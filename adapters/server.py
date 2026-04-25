"""
FastAPI 服务：WebUI + 预留 ClawBot HTTP 接口
"""
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.llm import PROVIDERS

logger = logging.getLogger(__name__)

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)


def create_app(agent_factory):
    """
    agent_factory: callable(provider_name) -> Agent
    接受 provider 名字，返回对应的 Agent 实例（用于前端切换 LLM）
    """
    app = FastAPI(title="Mini Agent", version="0.1.0")

    # ── 静态文件（WebUI）──────────────────────────────────
    webui_dir = Path("webui")
    if webui_dir.exists():
        app.mount("/static", StaticFiles(directory=str(webui_dir)), name="static")

    # ── 接口 ──────────────────────────────────────────────

    @app.get("/")
    def index():
        html = webui_dir / "index.html"
        if html.exists():
            return FileResponse(str(html))
        return JSONResponse({"status": "Mini Agent running. No WebUI found."})

    class ChatRequest(BaseModel):
        text: str
        image_paths: list = []
        provider: str = "kimi"

    @app.post("/api/chat")
    def chat(req: ChatRequest):
        logger.info(f"收到 /api/chat 请求：provider={req.provider}, text={req.text[:80]}")
        try:
            agent = agent_factory(req.provider)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        steps_out = []

        def on_step(step):
            steps_out.append({
                "type": step["type"],
                "name": step["name"],
                "args": step["args"],
                "result": step["result"][:500],  # 截断避免响应过大
            })

        try:
            reply, _ = agent.run(req.text, image_paths=req.image_paths or None, on_step=on_step)
        except Exception as e:
            logger.error(f"/api/chat 执行出错：{e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

        return {"reply": reply, "steps": steps_out}

    @app.post("/api/upload")
    def upload(file: UploadFile = File(...)):
        suffix = Path(file.filename or "upload").suffix or ""
        dest = UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(f"文件已上传：{dest}")
        return {"path": str(dest)}

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
