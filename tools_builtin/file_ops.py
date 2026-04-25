"""
内置工具：read / write（文件读写）
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_CHARS = 10_000

# write 只允许写入这些目录
_ALLOWED_WRITE_DIRS = ["workspace", "uploads", "logs"]


def read_file(path: str) -> str:
    """读取文件内容，超过 10000 字符截断，二进制文件返回错误"""
    p = Path(path)
    if not p.exists():
        return f"[error] 文件不存在：{path}"
    if not p.is_file():
        return f"[error] 路径不是文件：{path}"

    # 尝试以文本模式读取
    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"[error] 文件是二进制格式，无法读取：{path}"

    if len(content) > _MAX_CHARS:
        content = content[:_MAX_CHARS]
        return content + f"\n\n[内容已截断，只显示前 {_MAX_CHARS} 字符]"
    return content


def write_file(path: str, content: str) -> str:
    """向文件写入内容，只允许写入 workspace/、uploads/、logs/ 目录"""
    p = Path(path).resolve()

    # 安全限制：检查目标目录
    allowed = False
    for allowed_dir in _ALLOWED_WRITE_DIRS:
        # 相对路径检查：路径的第一个组件必须是允许的目录之一
        parts = Path(path).parts
        if parts and parts[0] in _ALLOWED_WRITE_DIRS:
            allowed = True
            break
        # 绝对路径检查：包含允许目录作为组件
        if allowed_dir in p.parts:
            allowed = True
            break

    if not allowed:
        return f"[error] 安全限制：write 只能写入 {', '.join(_ALLOWED_WRITE_DIRS)} 目录。目标路径：{path}"

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"文件已写入：{path}（{len(content)} 字符）"
    except Exception as e:
        logger.error(f"写文件失败：{path}，错误：{e}")
        return f"[error] 写文件失败：{e}"


def register(registry):
    """向 ToolRegistry 注册 read 和 write 工具"""
    registry.register(
        name="read",
        description="Read the content of a text file. Returns up to 10,000 characters.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (relative or absolute)"},
            },
            "required": ["path"],
        },
        handler=read_file,
    )

    registry.register(
        name="write",
        description="Write text content to a file. Creates parent directories if needed. Overwrites existing file. Only allowed in workspace/, uploads/, logs/ directories.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (must be under workspace/, uploads/, or logs/)"},
                "content": {"type": "string", "description": "Text content to write"},
            },
            "required": ["path", "content"],
        },
        handler=write_file,
    )
