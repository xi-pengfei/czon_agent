"""
Skill 扫描与加载：遵守 agentskills.io SKILL.md 规范
"""
import logging
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Optional, Dict

import yaml

logger = logging.getLogger(__name__)

# name 字段校验规则
_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$')
_MAX_NAME_LEN = 64
_MAX_DESC_LEN = 1024
_WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_SKILL_ARCHIVE_FILES = 5_000
MAX_SKILL_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_SKILL_UNPACKED_BYTES = 500 * 1024 * 1024


class SkillArchiveError(ValueError):
    pass


@dataclass
class SkillMeta:
    name: str
    description: str
    path: Path
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


class SkillLoader:
    def __init__(self, skills_dir: Path, enabled: Optional[list] = None):
        """
        skills_dir: skills/ 目录
        enabled: 白名单（None 表示全部启用）
        """
        self.skills_dir = skills_dir
        self.enabled = enabled
        self.catalog: Dict[str, SkillMeta] = {}

    def scan(self) -> None:
        """扫描目录，读取每个子目录的 SKILL.md frontmatter"""
        self.catalog.clear()
        if not self.skills_dir.exists():
            logger.warning(f"skills 目录不存在：{self.skills_dir}")
            return

        for subdir in sorted(self.skills_dir.iterdir()):
            if not subdir.is_dir():
                continue
            skill_file = subdir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                meta = self._parse_skill_file(skill_file, subdir)
                if meta is None:
                    continue
                # 白名单过滤
                if self.enabled is not None and meta.name not in self.enabled:
                    logger.debug(f"Skill '{meta.name}' 不在白名单中，跳过")
                    continue
                self.catalog[meta.name] = meta
                logger.info(f"已加载 skill：{meta.name}")
            except Exception as e:
                logger.error(f"解析 skill 失败（{skill_file}）：{e}")

    def _parse_skill_file(self, skill_file: Path, skill_dir: Path) -> Optional[SkillMeta]:
        """解析 SKILL.md，提取 frontmatter 并校验"""
        content = skill_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            logger.warning(f"{skill_file} 缺少 YAML frontmatter，跳过")
            return None

        # 提取 frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            logger.warning(f"{skill_file} frontmatter 格式不正确，跳过")
            return None

        try:
            fm = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            logger.error(f"{skill_file} frontmatter 解析失败：{e}")
            return None

        if not isinstance(fm, dict):
            logger.warning(f"{skill_file} frontmatter 不是 dict，跳过")
            return None

        # 必填字段验证
        name = fm.get("name", "")
        if not name:
            logger.warning(f"{skill_file} 缺少 name 字段，跳过")
            return None
        if len(name) > _MAX_NAME_LEN:
            logger.warning(f"{skill_file} name 超过 {_MAX_NAME_LEN} 字符，跳过")
            return None
        if not _NAME_RE.match(name):
            logger.warning(f"{skill_file} name '{name}' 不符合规范（只允许小写字母/数字/连字符），跳过")
            return None
        if "--" in name:
            logger.warning(f"{skill_file} name '{name}' 含连续连字符，跳过")
            return None

        description = fm.get("description", "")
        if not description:
            logger.warning(f"{skill_file} 缺少 description 字段，跳过")
            return None
        if len(description) > _MAX_DESC_LEN:
            logger.warning(f"{skill_file} description 超过 {_MAX_DESC_LEN} 字符，跳过")
            return None
        if "<" in description or ">" in description:
            logger.warning(f"{skill_file} description 含尖括号，跳过")
            return None

        return SkillMeta(
            name=name,
            description=description,
            path=skill_dir,
            license=fm.get("license"),
            compatibility=fm.get("compatibility"),
            metadata=fm.get("metadata", {}),
        )

    def get_catalog_text(self) -> str:
        """返回给 LLM 的目录说明（轻量元数据）"""
        if not self.catalog:
            return "Available skills: (none)"
        lines = ["Available skills (use activate_skill to load details):"]
        for name, meta in self.catalog.items():
            lines.append(f"  - {name}: {meta.description}")
        return "\n".join(lines)

    def load_body(self, name: str) -> str:
        """
        读取指定 skill 的 SKILL.md，去掉 frontmatter 返回正文。
        找不到抛 KeyError。
        """
        if name not in self.catalog:
            raise KeyError(name)
        skill_file = self.catalog[name].path / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content.strip()


def describe_skills(skills_dir: Path, settings: dict) -> list[dict]:
    loader = SkillLoader(Path(skills_dir), enabled=None)
    loader.scan()
    result = []
    for meta in loader.catalog.values():
        size, modified_at = _directory_stats(meta.path)
        setting = settings.get(meta.name, {})
        result.append({
            "name": meta.name,
            "description": meta.description,
            "path": str(meta.path.resolve()),
            "size": size,
            "modified_at": modified_at,
            "enabled": bool(setting.get("enabled", True)),
        })
    return result


def install_skill_archive(archive_path: Path, skills_dir: Path) -> str:
    skills_dir = Path(skills_dir).resolve()
    skills_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".skill-upload-", dir=skills_dir.parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = [item for item in archive.infolist() if not _ignored_archive_entry(item.filename)]
            files = [item for item in members if not item.is_dir()]
            if not files or len(files) > MAX_SKILL_ARCHIVE_FILES:
                raise SkillArchiveError("Skill 压缩包为空或文件数量过多")
            if sum(item.file_size for item in files) > MAX_SKILL_UNPACKED_BYTES:
                raise SkillArchiveError("Skill 解压后的总体积超过限制")
            seen_paths = set()
            for item in members:
                relative = _safe_archive_path(item)
                path_key = relative.as_posix().casefold()
                if path_key in seen_paths:
                    raise SkillArchiveError("Skill 压缩包包含重复路径")
                seen_paths.add(path_key)
                target = staging.joinpath(*relative.parts)
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

        skill_root = _archive_skill_root(staging)
        loader = SkillLoader(skill_root.parent, enabled=None)
        meta = loader._parse_skill_file(skill_root / "SKILL.md", skill_root)
        if meta is None:
            raise SkillArchiveError("SKILL.md 格式不合法")
        destination = skills_dir / meta.name
        if destination.exists():
            raise SkillArchiveError(f"Skill {meta.name} 已存在，请先删除后再上传")
        shutil.move(str(skill_root), destination)
        return meta.name
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        if isinstance(exc, SkillArchiveError):
            raise
        raise SkillArchiveError("无法读取或安装 Skill 压缩包") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def delete_skill(skills_dir: Path, name: str) -> None:
    if not _NAME_RE.fullmatch(name):
        raise KeyError(name)
    root = Path(skills_dir).resolve()
    loader = SkillLoader(root, enabled=None)
    loader.scan()
    meta = loader.catalog.get(name)
    if meta is None:
        raise KeyError(name)
    target = meta.path.resolve()
    target.relative_to(root)
    if meta.path.is_symlink():
        meta.path.unlink()
    else:
        shutil.rmtree(target)


def _directory_stats(root: Path) -> tuple[int, str]:
    size = 0
    modified_ns = root.stat().st_mtime_ns
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if not (Path(current) / name).is_symlink()]
        for name in files:
            path = Path(current) / name
            try:
                file_stat = path.stat(follow_symlinks=False)
            except OSError:
                continue
            size += file_stat.st_size
            modified_ns = max(modified_ns, file_stat.st_mtime_ns)
    modified_at = datetime.fromtimestamp(modified_ns / 1_000_000_000, tz=timezone.utc).isoformat()
    return size, modified_at


def _ignored_archive_entry(name: str) -> bool:
    normalized = name.replace("\\", "/").strip("/")
    return not normalized or normalized == "__MACOSX" or normalized.startswith("__MACOSX/") or normalized.endswith("/.DS_Store") or normalized == ".DS_Store"


def _safe_archive_path(item: zipfile.ZipInfo) -> PurePosixPath:
    name = item.filename
    if "\\" in name or name.startswith("/") or item.flag_bits & 0x1 or len(name) > 240:
        raise SkillArchiveError("Skill 压缩包包含不安全路径或加密文件")
    path = PurePosixPath(name)
    if any(
        part in {"", ".", ".."}
        or ":" in part
        or any(ord(char) < 32 for char in part)
        or part.rstrip(" .") != part
        or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
        for part in path.parts
    ):
        raise SkillArchiveError("Skill 压缩包包含不安全路径")
    mode = (item.external_attr >> 16) & 0o170000
    if mode == stat.S_IFLNK:
        raise SkillArchiveError("Skill 压缩包不能包含符号链接")
    return path


def _archive_skill_root(staging: Path) -> Path:
    if (staging / "SKILL.md").is_file():
        return staging
    children = [path for path in staging.iterdir() if path.name != ".DS_Store"]
    if len(children) == 1 and children[0].is_dir() and (children[0] / "SKILL.md").is_file():
        return children[0]
    raise SkillArchiveError("压缩包必须包含一个带有 SKILL.md 的 Skill 目录")
