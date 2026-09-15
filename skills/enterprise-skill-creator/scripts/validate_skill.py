#!/usr/bin/env python3
"""Validate and optionally package an enterprise Agent Skill draft."""

import argparse
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from core.skills import skill_files, validate_skill


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查并打包 Agent Skill 草稿")
    parser.add_argument("skill_dir", type=Path, help="Skill 草稿目录")
    parser.add_argument("--package", type=Path, help="验证通过后生成 ZIP 的路径")
    return parser.parse_args()


def package_skill(root: Path, output: Path) -> Path:
    root = root.expanduser().resolve()
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if root == output or root in output.parents:
        raise ValueError("ZIP 输出路径不能位于 Skill 草稿目录内")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in skill_files(root):
                if not path.is_symlink():
                    archive.write(path, (Path(root.name) / path.relative_to(root)).as_posix())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def main() -> int:
    args = parse_args()
    result = validate_skill(args.skill_dir)
    if args.package and result["ok"]:
        try:
            result["package"] = str(package_skill(args.skill_dir, args.package))
        except (OSError, ValueError) as exc:
            result["ok"] = False
            result["checks"].append({"name": "打包", "ok": False, "detail": str(exc)})
    elif args.package:
        result["package"] = None
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
