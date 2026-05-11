#!/usr/bin/env python3
"""
vector-store 冒烟测试

Level 1（无外部依赖）：切片逻辑
Level 2（需 Qdrant）：  manage.py — collection 创建/查看/删除
Level 3（需 Qdrant + QWEN_API_KEY）：ingest + search 全流程

用法：
  python skills/vector-store/scripts/test_smoke.py          # 只跑 Level 1
  python skills/vector-store/scripts/test_smoke.py --level 2  # Level 1+2
  python skills/vector-store/scripts/test_smoke.py --level 3  # 全部
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # czon_agent/
SCRIPTS = Path(__file__).resolve().parent


def load_ingest():
    spec = importlib.util.spec_from_file_location("ingest", SCRIPTS / "ingest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(cmd: list, env=None) -> dict:
    e = {**os.environ, **(env or {})}
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=e)
    return {"ok": r.returncode == 0, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}


def check(label: str, ok: bool, detail: str = ""):
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}" + (f"\n    {detail}" if detail and not ok else ""))
    if not ok:
        sys.exit(1)


# ── Level 1：切片逻辑 ─────────────────────────────────────────────────────────

def test_level1():
    print("\n[Level 1] 切片逻辑（无外部依赖）")
    ingest = load_ingest()

    # 默认段落切片
    text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
    chunks = ingest.chunk_default(text)
    check("默认段落切片：数量正确", len(chunks) == 3, f"得到 {len(chunks)} 块")
    check("默认切片：内容完整", "第一段" in chunks[0])

    # law 模式切片
    # 注意：前言"总则"会被切成独立一块，3条法规共4块，这是正确行为
    law_text = "总则\n\n第一条 本法适用于中华人民共和国境内。\n\n第二条 当事人依法享有自愿订立合同的权利。\n\n第三条 任何单位和个人不得非法干预。"
    chunks = ingest.chunk_law(law_text)
    check("law 模式：前言+3条共4块", len(chunks) == 4, f"得到 {len(chunks)} 块")
    check("law 模式：第二块包含'第一条'", "第一条" in chunks[1])

    # 空内容兜底
    chunks = ingest.chunk_text("", "default")
    check("空内容兜底：不崩溃", isinstance(chunks, list))

    print("  → Level 1 全部通过")


# ── Level 2：Qdrant 连通 + manage ─────────────────────────────────────────────

def test_level2():
    print("\n[Level 2] Qdrant 连通 + collection 管理")
    COL = "test-smoke-col"
    py = str(sys.executable)
    script = str(SCRIPTS / "manage.py")

    # list
    r = run([py, script, "list"])
    check("Qdrant 连通（list）", r["ok"], r["stderr"])

    # create
    r = run([py, script, "create", "--collection", COL])
    check("创建 collection", r["ok"], r["stderr"])

    # info
    r = run([py, script, "info", "--collection", COL])
    check("查看 collection info", r["ok"], r["stderr"])

    # delete
    r = run([py, script, "delete", "--collection", COL])
    check("删除 collection", r["ok"], r["stderr"])

    print("  → Level 2 全部通过")


# ── Level 3：ingest + search 全流程 ──────────────────────────────────────────

def test_level3():
    print("\n[Level 3] ingest + search 全流程")
    api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("  ✗ 缺少 QWEN_API_KEY / DASHSCOPE_API_KEY，跳过 Level 3")
        sys.exit(1)

    COL = "test-smoke-law"
    py = str(sys.executable)

    # 写一个临时法规文件
    law_content = """第一条 本法适用于中华人民共和国境内的自然人、法人和非法人组织。

第二条 当事人依法享有自愿订立合同的权利，任何单位和个人不得非法干预。

第五百七十七条 当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(law_content)
        tmp_path = f.name

    try:
        # ingest
        r = run([py, str(SCRIPTS / "ingest.py"), "--file", tmp_path,
                 "--collection", COL, "--mode", "law", "--category", "合同法"])
        check("ingest 成功", r["ok"], r["stderr"])
        data = json.loads(r["stdout"])
        check("ingest 切入 3 条", data.get("chunks_stored") == 3, str(data))

        # search
        r = run([py, str(SCRIPTS / "search.py"),
                 "--query", "不履行合同义务怎么办", "--collection", COL, "--top-k", "3"])
        check("search 成功", r["ok"], r["stderr"])
        data = json.loads(r["stdout"])
        hits = data.get("hits", [])
        check("search 返回结果", len(hits) > 0, str(data))
        check("首条相似度 > 0.5", hits[0]["score"] > 0.5, f"score={hits[0]['score']}")
        print(f"    首条：score={hits[0]['score']}  内容={hits[0]['content'][:40]}…")

    finally:
        os.unlink(tmp_path)
        # 清理测试 collection
        run([py, str(SCRIPTS / "manage.py"), "delete", "--collection", COL])
        print("  （测试 collection 已清理）")

    print("  → Level 3 全部通过")


# ── 入口 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", type=int, default=1, choices=[1, 2, 3])
    args = parser.parse_args()

    test_level1()
    if args.level >= 2:
        test_level2()
    if args.level >= 3:
        test_level3()

    print("\n所有测试通过 ✓")


if __name__ == "__main__":
    main()
