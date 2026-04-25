"""
CLI 适配器：单次执行 + 交互式 REPL
"""
import logging
import sys
from typing import Optional, List

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

logger = logging.getLogger(__name__)
console = Console()


def run_once(agent, text: str, image_paths: Optional[List[str]] = None):
    """执行单次请求并打印结果"""
    console.print(f"[bold cyan]用户:[/bold cyan] {text}")
    if image_paths:
        console.print(f"[dim]图片：{image_paths}[/dim]")

    def on_step(step):
        args_summary = str(step["args"])[:80]
        console.print(f"  [yellow]🔧 {step['name']}({args_summary})[/yellow]")

    try:
        reply, steps = agent.run(text, image_paths=image_paths, on_step=on_step)
        console.print()
        console.print(Panel(Markdown(reply), title="[bold green]Agent 回复[/bold green]", border_style="green"))
        return reply
    except Exception as e:
        logger.error(f"执行出错：{e}", exc_info=True)
        console.print(f"[bold red]错误：{e}[/bold red]")
        sys.exit(1)


def run_interactive(agent):
    """交互式 REPL 模式"""
    console.print(Panel(
        "[bold]Mini Agent — 交互模式[/bold]\n输入消息后按 Enter 发送，输入 [cyan]exit[/cyan] 或 [cyan]quit[/cyan] 退出",
        border_style="blue",
    ))

    while True:
        try:
            text = console.input("[bold cyan]>>> [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]已退出[/dim]")
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit", "q"):
            console.print("[dim]再见！[/dim]")
            break

        def on_step(step):
            args_summary = str(step["args"])[:80]
            console.print(f"  [yellow]🔧 {step['name']}({args_summary})[/yellow]")

        try:
            reply, _ = agent.run(text, on_step=on_step)
            console.print()
            console.print(Panel(Markdown(reply), title="[bold green]Agent[/bold green]", border_style="green"))
            console.print()
        except Exception as e:
            logger.error(f"执行出错：{e}", exc_info=True)
            console.print(f"[bold red]错误：{e}[/bold red]\n")
