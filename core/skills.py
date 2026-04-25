"""
Skill 扫描与加载：遵守 agentskills.io SKILL.md 规范
"""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict

import yaml

logger = logging.getLogger(__name__)

# name 字段校验规则
_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$')
_MAX_NAME_LEN = 64
_MAX_DESC_LEN = 1024


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
