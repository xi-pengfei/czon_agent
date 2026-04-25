"""
内置工具：activate_skill（按需加载 skill 详情）
"""
import logging

logger = logging.getLogger(__name__)


def make_activate_skill(skill_loader):
    """工厂函数：绑定 skill_loader 实例，返回 activate_skill 处理函数"""

    def activate_skill(name: str) -> str:
        """
        加载指定 skill 的完整 SKILL.md 正文。
        找不到时返回错误字符串 + 可用列表。
        """
        try:
            body = skill_loader.load_body(name)
            logger.info(f"Skill '{name}' 已激活，正文长度 {len(body)}")
            return body
        except KeyError:
            available = ", ".join(skill_loader.catalog.keys()) or "（无）"
            return f"[error] skill '{name}' 不存在。可用 skill：{available}"

    return activate_skill


def register(registry, skill_loader):
    """向 ToolRegistry 注册 activate_skill 工具"""
    registry.register(
        name="activate_skill",
        description="Load the full instructions of a specific skill. Use this BEFORE running any skill-related command. The returned text is the skill's complete SKILL.md body.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Exact skill name from the catalog"},
            },
            "required": ["name"],
        },
        handler=make_activate_skill(skill_loader),
    )
