from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.types import TextContent, ToolAnnotations
from pydantic import Field

from .desktop import DesktopBackend, Window, create_backend


VISUAL_TERMS = {
    "visual", "vision", "color", "colour", "layout", "appearance", "image", "icon", "chart",
    "graph", "diagram", "photo", "picture", "logo", "position", "shape", "colorful", "screenshot",
    "video", "animation", "alignment", "spacing", "font",
    "màu", "mau", "bố cục", "bo cuc", "hình", "hinh", "ảnh", "anh", "biểu đồ", "bieu do",
    "sơ đồ", "so do", "giao diện", "giao dien", "vị trí", "vi tri", "biểu tượng", "bieu tuong",
    "màn hình", "man hinh",
}
VISUAL_PHRASES = {
    "what is on screen", "what's on screen", "what is shown", "what is visible",
    "what is currently on screen",
    "what does it look like", "describe the screen", "what am i seeing",
    "đang hiển thị", "dang hien thi", "trông như thế nào", "trong nhu the nao",
    "mô tả màn hình", "mo ta man hinh", "tôi đang thấy gì", "toi dang thay gi",
}

server = MCPServer(
    "AncharView",
    instructions=(
        "Use observe_screen with the task goal. It targets the foreground window by default, returns a bounded "
        "accessibility tree, and includes a cropped image only when visual_mode or accessibility coverage calls for it."
    ),
)
_backend: DesktopBackend | None = None


def backend() -> DesktopBackend:
    global _backend
    if _backend is None:
        _backend = create_backend()
    return _backend


def _window(window_id: str | None) -> Window:
    desktop = backend()
    if window_id is None:
        return desktop.foreground_window()
    if hasattr(desktop, "window_by_id"):
        return desktop.window_by_id(window_id)
    for item in desktop.list_windows():
        if item.window_id == window_id:
            return item
    raise ValueError("Unknown window_id. Call list_windows and choose a current window.")


def _tokens(text: str) -> set[str]:
    return {part.casefold() for part in re.findall(r"[\w-]+", text, flags=re.UNICODE) if len(part) > 1}


def _rank_nodes(nodes: list[dict], task_goal: str) -> None:
    goal_tokens = _tokens(task_goal)
    for node in nodes:
        label = " ".join((node.get("name", ""), node.get("automation_id", ""), node.get("role", "")))
        node_tokens = _tokens(label)
        matches = sorted(goal_tokens & node_tokens)
        node["task_matches"] = matches
        node["relevance"] = round(len(matches) / max(1, len(goal_tokens)), 3)


def _select_context(
    nodes: list[dict], task_goal: str, detail: str, max_nodes: int
) -> list[dict]:
    if detail == "full":
        return nodes[:max_nodes]

    visible = [node for node in nodes if node.get("visible", True)]
    by_id = {node["element_id"]: node for node in visible if node.get("element_id")}
    interactive = [
        node for node in visible
        if node.get("patterns") or node.get("focused") or node.get("relevance", 0) > 0
    ]
    matching = [node for node in visible if node.get("relevance", 0) > 0]

    if detail == "minimal":
        seeds = [node for node in visible if node.get("focused")]
        seeds.extend(node for node in matching if node not in seeds)
        if not seeds:
            seeds = interactive[:1]
    else:
        seeds = matching or interactive

    selected_ids: set[str] = set()
    for seed in sorted(
        seeds,
        key=lambda node: (
            not bool(node.get("focused")),
            -float(node.get("relevance", 0)),
        ),
    ):
        path: list[dict] = [seed]
        parent_id = seed.get("parent_id")
        while parent_id in by_id:
            parent = by_id[parent_id]
            path.append(parent)
            parent_id = parent.get("parent_id")
        addition = {node["element_id"] for node in path if node.get("element_id")}
        if len(selected_ids | addition) <= max_nodes:
            selected_ids.update(addition)

    return [node for node in visible if node.get("element_id") in selected_ids][:max_nodes]


def _visual_decision(nodes: list[dict], task_goal: str, visual_mode: str) -> tuple[bool, str]:
    if visual_mode == "always":
        return True, "requested by visual_mode=always"
    if visual_mode == "never":
        return False, "disabled by visual_mode=never"

    goal = task_goal.casefold()
    if any(term in goal for term in VISUAL_TERMS) or any(phrase in goal for phrase in VISUAL_PHRASES):
        return True, "task_goal asks about visual appearance or image content"

    labelled = sum(bool(node.get("name") or node.get("automation_id")) for node in nodes)
    coverage = labelled / max(1, len(nodes))
    if len(nodes) < 4 or labelled < 2 or coverage < 0.2:
        return True, "accessibility tree has insufficient labelled content"
    return False, "accessibility tree provides sufficient semantic content for this task"


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def list_windows() -> str:
    """List visible top-level desktop windows. Use a returned window_id to inspect a specific app."""
    return json.dumps([window.__dict__ for window in backend().list_windows()], ensure_ascii=False)


@server.tool()
def observe_screen(
    task_goal: Annotated[str, Field(description="What the agent is trying to do or learn from the current screen.")] = "",
    window_id: Annotated[str | None, Field(description="Optional window_id from list_windows; defaults to the foreground window.")] = None,
    visual_mode: Literal["auto", "always", "never"] = "auto",
    detail: Annotated[Literal["minimal", "interactive", "full"], Field(description="Context size: minimal matches/focus, interactive controls relevant to the task, or full accessible tree.")] = "interactive",
    max_nodes: Annotated[int, Field(ge=1, le=1200, description="Maximum accessibility elements to return.")] = 300,
) -> list[TextContent | Image]:
    """Observe the foreground app for the given task; return relevant accessibility data and attach a cropped image only when needed."""
    desktop = backend()
    window = _window(window_id)
    inspected_nodes, truncated = desktop.inspect(window, max_nodes)
    _rank_nodes(inspected_nodes, task_goal)
    nodes = _select_context(inspected_nodes, task_goal, detail, max_nodes)
    include_image, reason = _visual_decision(inspected_nodes, task_goal, visual_mode)

    result = {
        "platform": desktop.name,
        "window": window.__dict__,
        "task_goal": task_goal,
        "detail": detail,
        "accessibility": {
            "node_count": len(nodes),
            "inspected_node_count": len(inspected_nodes),
            "filtered": len(nodes) < len(inspected_nodes),
            "truncated": truncated or len(inspected_nodes) >= max_nodes,
            "nodes": nodes,
        },
        "vision": {
            "included": include_image,
            "reason": reason,
            "scope": "selected-window crop",
        },
    }
    content: list[TextContent | Image] = [
        TextContent(type="text", text=json.dumps(result, ensure_ascii=False))
    ]
    if include_image:
        try:
            content.append(Image(data=desktop.capture(window), format="png"))
        except Exception as error:
            result["vision"]["included"] = False
            result["vision"]["error"] = str(error)
            content[0] = TextContent(type="text", text=json.dumps(result, ensure_ascii=False))
    return content


@server.tool()
def capture_screen(
    window_id: Annotated[str | None, Field(description="Optional window_id; defaults to the foreground window.")] = None,
) -> Image:
    """Explicitly capture the selected window as a PNG, even when observe_screen auto mode would omit vision."""
    return Image(data=backend().capture(_window(window_id)), format="png")


@server.tool()
def click_element(element_id: str) -> str:
    """Activate an element_id returned by a recent observe_screen call using the platform accessibility API."""
    return backend().click(element_id)


@server.tool()
def set_text(element_id: str, text: str) -> str:
    """Set text through Windows UIA or Linux AT-SPI EditableText without reading the resulting value back."""
    return backend().set_text(element_id, text)


def main() -> None:
    server.run()
