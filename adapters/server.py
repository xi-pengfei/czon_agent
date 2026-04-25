"""
FastAPI 服务：WebUI + 预留 ClawBot HTTP 接口
"""
import json
import logging
import mimetypes
import queue
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.llm import PROVIDERS

logger = logging.getLogger(__name__)

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 80_000


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _step_for_response(step: dict) -> dict:
    return {
        "type": step["type"],
        "id": step.get("id"),
        "name": step["name"],
        "args": step["args"],
        "result": step.get("result"),
    }


def _is_confirmation_step(step: dict) -> bool:
    result = step.get("result") or {}
    error = result.get("error") if isinstance(result, dict) else None
    return bool(error and error.get("type") == "ConfirmationRequired")


def _message_chars(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages)


def _trim_history(messages: list[dict]) -> list[dict]:
    result = list(messages)[-MAX_HISTORY_MESSAGES:]
    while result and _message_chars(result) > MAX_HISTORY_CHARS:
        result.pop(0)
    return result


def _user_history_text(text: str, attachments: list) -> str:
    if not attachments:
        return text
    names = []
    for item in attachments:
        if isinstance(item, dict):
            names.append(item.get("name") or item.get("path") or "attachment")
        else:
            names.append(str(item))
    return f"{text}\n\n[附件：{', '.join(names)}]"


def create_app(agent_factory, workspace_dir: str = "./workspace"):
    """
    agent_factory: callable(provider_name) -> Agent
    接受 provider 名字，返回对应的 Agent 实例（用于前端切换 LLM）
    """
    app = FastAPI(title="czon Agent", version="0.1.0")
    pending_confirmations = {}
    pending_lock = threading.Lock()
    sessions = {}
    session_lock = threading.Lock()
    workspace_root = Path(workspace_dir).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    def get_history(session_id: str) -> list[dict]:
        with session_lock:
            return list(sessions.get(session_id, []))

    def append_history(session_id: str, user_text: str, attachments: list, assistant_text: str) -> None:
        if not session_id:
            return
        with session_lock:
            history = sessions.setdefault(session_id, [])
            history.append({"role": "user", "content": _user_history_text(user_text, attachments)})
            history.append({"role": "assistant", "content": assistant_text or ""})
            sessions[session_id] = _trim_history(history)

    def register_confirmation(step: dict, provider: str) -> dict:
        if not _is_confirmation_step(step):
            return step

        result = step["result"]
        confirmation = result.setdefault("meta", {}).setdefault("confirmation", {})
        confirmation_id = uuid.uuid4().hex
        confirmation["id"] = confirmation_id
        confirmation["provider"] = provider

        with pending_lock:
            pending_confirmations[confirmation_id] = {
                "provider": provider,
                "tool_name": confirmation.get("tool_name") or step["name"],
                "args": confirmation.get("args") or step["args"],
            }
        return step

    # ── 静态文件（WebUI）──────────────────────────────────
    webui_dir = Path("webui")
    if webui_dir.exists():
        app.mount("/static", StaticFiles(directory=str(webui_dir)), name="static")

    # ── 接口 ──────────────────────────────────────────────

    @app.get("/")
    def index():
        html = webui_dir / "index.html"
        if html.exists():
            response = FileResponse(str(html))
            response.headers["Cache-Control"] = "no-store"
            return response
        return JSONResponse({"status": "czon Agent running. No WebUI found."})

    class ChatRequest(BaseModel):
        text: str
        attachments: list = Field(default_factory=list)
        provider: str = "kimi"
        session_id: str = ""

    class ConfirmRequest(BaseModel):
        confirmation_id: str

    class ResetSessionRequest(BaseModel):
        session_id: str

    @app.post("/api/chat")
    def chat(req: ChatRequest):
        logger.info(f"收到 /api/chat 请求：provider={req.provider}, text={req.text[:80]}")
        try:
            agent = agent_factory(req.provider)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        steps_out = []

        def on_step(step):
            steps_out.append(_step_for_response(register_confirmation(step, req.provider)))

        try:
            reply, _ = agent.run(
                req.text,
                attachments=req.attachments or None,
                history=get_history(req.session_id),
                on_step=on_step,
            )
            append_history(req.session_id, req.text, req.attachments, reply)
        except Exception as e:
            logger.error(f"/api/chat 执行出错：{e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

        return {"reply": reply, "steps": steps_out}

    @app.post("/api/chat/stream")
    def chat_stream(req: ChatRequest):
        logger.info(f"收到 /api/chat/stream 请求：provider={req.provider}, text={req.text[:80]}")

        def event_gen():
            events = queue.Queue()

            def run_agent():
                try:
                    try:
                        agent = agent_factory(req.provider)
                    except Exception as e:
                        events.put(("agent_error", {"error": str(e)}))
                        return

                    def on_step(step):
                        step_out = _step_for_response(register_confirmation(step, req.provider))
                        result = step_out.get("result") or {}
                        error = result.get("error") if isinstance(result, dict) else None
                        event_name = "confirmation_required" if error and error.get("type") == "ConfirmationRequired" else "tool_result"
                        events.put((event_name, step_out))

                    def on_delta(text: str):
                        events.put(("assistant_delta", {"text": text}))

                    events.put(("agent_start", {"provider": req.provider, "text": req.text}))
                    reply, steps = agent.run(
                        req.text,
                        attachments=req.attachments or None,
                        history=get_history(req.session_id),
                        on_step=on_step,
                        on_delta=on_delta,
                    )
                    append_history(req.session_id, req.text, req.attachments, reply)
                    events.put(("agent_done", {"reply": reply, "steps_count": len(steps)}))
                except Exception as e:
                    logger.error("/api/chat/stream 执行出错：%s", e, exc_info=True)
                    events.put(("agent_error", {"error": str(e)}))
                finally:
                    events.put(None)

            threading.Thread(target=run_agent, daemon=True).start()

            while True:
                item = events.get()
                if item is None:
                    break
                event_name, data = item
                yield _sse(event_name, data)

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @app.post("/api/tool/confirm")
    def confirm_tool(req: ConfirmRequest):
        with pending_lock:
            pending = pending_confirmations.pop(req.confirmation_id, None)

        if not pending:
            raise HTTPException(status_code=404, detail="确认请求不存在或已过期")

        try:
            agent = agent_factory(pending["provider"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        result = agent.tool_registry.execute(
            pending["tool_name"],
            pending["args"],
            confirmed=True,
        )
        step = {
            "type": "tool_call",
            "name": pending["tool_name"],
            "args": pending["args"],
            "result": result.to_dict(),
        }
        return {"confirmation_id": req.confirmation_id, "step": step}

    @app.post("/api/session/reset")
    def reset_session(req: ResetSessionRequest):
        with session_lock:
            sessions.pop(req.session_id, None)
        return {"ok": True}

    @app.post("/api/upload")
    def upload(file: UploadFile = File(...)):
        suffix = Path(file.filename or "upload").suffix or ""
        dest = UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(f"文件已上传：{dest}")
        mime = file.content_type or mimetypes.guess_type(str(dest))[0] or "application/octet-stream"
        return {
            "path": str(dest),
            "name": file.filename or dest.name,
            "mime": mime,
            "size": dest.stat().st_size,
        }

    @app.get("/download/{file_path:path}")
    def download_workspace_file(file_path: str):
        target = (workspace_root / file_path).resolve()
        try:
            target.relative_to(workspace_root)
        except ValueError:
            raise HTTPException(status_code=403, detail="不允许访问 workspace 外的文件")

        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")

        return FileResponse(str(target), filename=target.name)

    @app.get("/api/providers")
    def get_providers():
        import os
        result = []
        for name, cfg in PROVIDERS.items():
            result.append({
                "name": name,
                "supports_vision": cfg["supports_vision"],
                "configured": bool(os.getenv(cfg["env_key"], "")),
            })
        return result

    return app
