from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image as PillowImage
from mss import mss


@dataclass(frozen=True)
class Window:
    window_id: str
    title: str
    process_id: int | None
    bounds: dict[str, int] | None


@dataclass
class CachedElement:
    platform: str
    value: Any
    created_at: float
    window_id: str | None = None
    bounds: dict[str, int] | None = None
    summary: str = ""


ELEMENT_TTL_SECONDS = 120
MAX_CACHED_ELEMENTS = 8000
_elements: dict[str, CachedElement] = {}
_windows: dict[str, Any] = {}
_next_id = 0
_TEXT_VALUE_ROLES = {
    "windows": {"edit", "password", "text box", "combobox"},
    "linux": {"entry", "password text", "text", "text entry", "combo box"},
}


def _is_text_value_role(platform: str, role: str) -> bool:
    return role.casefold() in _TEXT_VALUE_ROLES.get(platform, set())


def _select_active_window(windows: list[Window], active_window_ids: set[str]) -> Window:
    active_windows = [window for window in windows if window.window_id in active_window_ids]
    if len(active_windows) != 1:
        raise RuntimeError(
            "AT-SPI could not identify exactly one active window. Call list_windows and pass an explicit window_id."
        )
    return active_windows[0]


def _can_coordinate_fallback(
    observed_window_id: str | None,
    observed_bounds: dict[str, int] | None,
    foreground_window_id: str,
    current_bounds: dict[str, int] | None,
    visible: bool,
    enabled: bool,
) -> bool:
    return bool(
        observed_window_id
        and observed_window_id == foreground_window_id
        and observed_bounds
        and current_bounds == observed_bounds
        and visible
        and enabled
    )


def _element_summary(role: str, name: str) -> str:
    safe_name = "".join(character for character in name if character.isprintable())[:80]
    if not safe_name:
        return role
    return f"{role} named {json.dumps(safe_name, ensure_ascii=False)}"


def _new_id(prefix: str) -> str:
    global _next_id
    _next_id += 1
    return f"{prefix}{_next_id:x}"


def cache_element(
    platform: str,
    value: Any,
    window_id: str | None = None,
    bounds: dict[str, int] | None = None,
    summary: str = "",
) -> str:
    element_id = _new_id("e")
    _elements[element_id] = CachedElement(platform, value, time.monotonic(), window_id, bounds, summary)
    while len(_elements) > MAX_CACHED_ELEMENTS:
        _elements.pop(next(iter(_elements)))
    return element_id


def resolve_element(element_id: str, platform: str) -> Any:
    return resolve_cached_element(element_id, platform).value


def resolve_cached_element(element_id: str, platform: str) -> CachedElement:
    cached = _elements.get(element_id)
    if cached is None or cached.platform != platform:
        raise ValueError("Unknown element_id. Call observe_screen and use a recent ID.")
    if time.monotonic() - cached.created_at > ELEMENT_TTL_SECONDS:
        _elements.pop(element_id, None)
        raise ValueError("This element_id expired. Call observe_screen for a fresh ID.")
    return cached


class DesktopBackend:
    name = "base"

    def list_windows(self) -> list[Window]:
        raise NotImplementedError

    def foreground_window(self) -> Window:
        raise NotImplementedError

    def inspect(self, window: Window, max_nodes: int) -> tuple[list[dict[str, Any]], bool]:
        raise NotImplementedError

    def click(self, element_id: str) -> str:
        raise NotImplementedError

    def set_text(self, element_id: str, text: str) -> str:
        raise NotImplementedError

    def element_summary(self, element_id: str) -> str:
        cached = resolve_cached_element(element_id, self.name)
        return cached.summary or "desktop control"

    def capture(self, window: Window) -> bytes:
        bounds = window.bounds
        if (
            bounds is None
            or not {"x", "y", "width", "height"}.issubset(bounds)
            or bounds["width"] <= 0
            or bounds["height"] <= 0
        ):
            raise RuntimeError("Cannot safely capture the selected window because its bounds are unavailable or invalid.")

        if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY"):
            grim = shutil.which("grim")
            if not grim:
                raise RuntimeError("Wayland capture needs grim; the compositor may otherwise deny screenshots.")
            geometry = f"{bounds['x']},{bounds['y']} {bounds['width']}x{bounds['height']}"
            command = [grim, "-g", geometry]
            command.append("-")
            result = subprocess.run(command, capture_output=True, check=False)
            if result.returncode:
                detail = result.stderr.decode(errors="replace").strip()
                raise RuntimeError(f"grim could not capture the current window: {detail or 'capture denied'}")
            return result.stdout

        with mss() as screenshotter:
            area = {
                "left": bounds["x"],
                "top": bounds["y"],
                "width": bounds["width"],
                "height": bounds["height"],
            }
            shot = screenshotter.grab(area)
            image = PillowImage.frombytes("RGB", shot.size, shot.rgb)
            output = BytesIO()
            image.save(output, format="PNG", optimize=False)
            return output.getvalue()


class WindowsBackend(DesktopBackend):
    name = "windows"

    def __init__(self) -> None:
        try:
            from pywinauto import Desktop
        except ImportError as error:
            raise RuntimeError("Install the Windows extra with: python -m pip install -e '.[windows]'") from error
        self._desktop = Desktop(backend="uia")

    @staticmethod
    def _rect(wrapper: Any) -> dict[str, int] | None:
        try:
            rect = wrapper.rectangle()
            if rect.width() <= 0 or rect.height() <= 0:
                return None
            return {"x": rect.left, "y": rect.top, "width": rect.width(), "height": rect.height()}
        except Exception:
            return None

    def list_windows(self) -> list[Window]:
        results: list[Window] = []
        for wrapper in self._desktop.windows(visible_only=True):
            try:
                handle = int(wrapper.handle)
                window_id = str(handle)
                _windows[window_id] = wrapper
                results.append(Window(window_id, wrapper.window_text(), wrapper.process_id(), self._rect(wrapper)))
            except Exception:
                continue
        return results

    def foreground_window(self) -> Window:
        handle = int(ctypes.windll.user32.GetForegroundWindow())
        if not handle:
            raise RuntimeError("Windows has no foreground window.")
        return self.window_by_id(str(handle))

    def window_by_id(self, window_id: str) -> Window:
        try:
            handle = int(window_id, 0) if window_id.lower().startswith("0x") else int(window_id)
        except ValueError as error:
            raise ValueError("Windows window_id must be a decimal or hexadecimal handle.") from error
        wrapper = self._desktop.window(handle=handle).wrapper_object()
        _windows[str(handle)] = wrapper
        return Window(str(handle), wrapper.window_text(), wrapper.process_id(), self._rect(wrapper))

    def inspect(self, window: Window, max_nodes: int) -> tuple[list[dict[str, Any]], bool]:
        root = _windows.get(window.window_id)
        if root is None:
            root = self._desktop.window(handle=int(window.window_id)).wrapper_object()
        pending: list[tuple[Any, str | None, int]] = [(root, None, 0)]
        nodes: list[dict[str, Any]] = []
        truncated = False

        while pending and len(nodes) < max_nodes:
            wrapper, parent_id, depth = pending.pop()
            try:
                info = wrapper.element_info
                control_type = str(getattr(info, "control_type", "Control"))
                name = "" if _is_text_value_role(self.name, control_type) else str(wrapper.window_text() or "")
                automation_id = str(getattr(info, "automation_id", "") or "")
                rect = self._rect(wrapper)
                element_id = cache_element(
                    self.name,
                    wrapper,
                    window.window_id,
                    rect,
                    _element_summary(control_type, name),
                )
                patterns = _windows_patterns(control_type)
                nodes.append({
                    "element_id": element_id,
                    "parent_id": parent_id,
                    "depth": depth,
                    "role": control_type,
                    "name": name,
                    "automation_id": automation_id,
                    "enabled": bool(wrapper.is_enabled()),
                    "visible": bool(wrapper.is_visible()),
                    "focused": bool(getattr(info, "has_keyboard_focus", False)),
                    "bounds": rect,
                    "patterns": patterns,
                })
                if depth >= 12:
                    truncated = truncated or bool(wrapper.children())
                    continue
                children = wrapper.children()
                available = max_nodes - len(nodes) - len(pending)
                if len(children) > available:
                    truncated = True
                    children = children[:available]
                pending.extend((child, element_id, depth + 1) for child in reversed(children))
            except Exception:
                continue

        return nodes, truncated or bool(pending)

    def click(self, element_id: str) -> str:
        cached = resolve_cached_element(element_id, self.name)
        wrapper = cached.value
        if not wrapper.is_enabled():
            raise RuntimeError("The requested element is disabled.")
        try:
            wrapper.invoke()
            return "Element invoked through UI Automation."
        except Exception as error:
            try:
                current_bounds = self._rect(wrapper)
                foreground_window_id = str(int(ctypes.windll.user32.GetForegroundWindow()))
                safe_to_fallback = _can_coordinate_fallback(
                    cached.window_id,
                    cached.bounds,
                    foreground_window_id,
                    current_bounds,
                    bool(wrapper.is_visible()),
                    bool(wrapper.is_enabled()),
                )
            except Exception:
                safe_to_fallback = False
            if not safe_to_fallback:
                raise RuntimeError(
                    "UI Automation invocation failed and coordinate fallback was withheld because the target could have changed. Re-observe the window."
                ) from error
            wrapper.click_input()
            return "Element clicked through Windows UI Automation input."

    def set_text(self, element_id: str, text: str) -> str:
        wrapper = resolve_element(element_id, self.name)
        if not wrapper.is_enabled():
            raise RuntimeError("The requested element is disabled.")
        setter = getattr(wrapper, "set_edit_text", None)
        if not callable(setter):
            raise RuntimeError("The element does not expose an editable text control.")
        setter(text)
        return "Text set; AncharView did not read the value back."


class LinuxBackend(DesktopBackend):
    name = "linux"

    def __init__(self) -> None:
        try:
            import pyatspi
        except ImportError as error:
            raise RuntimeError(
                "Linux accessibility needs the distribution's AT-SPI Python binding "
                "(for Debian/Ubuntu: sudo apt install python3-pyatspi at-spi2-core)."
            ) from error
        self._atspi = pyatspi

    @staticmethod
    def _name(accessible: Any) -> str:
        try:
            return str(accessible.name or "")
        except Exception:
            return ""

    @staticmethod
    def _role(accessible: Any) -> str:
        try:
            return str(accessible.getRoleName() or "Unknown")
        except Exception:
            return "Unknown"

    def _bounds(self, accessible: Any) -> dict[str, int] | None:
        try:
            extents = accessible.queryComponent().getExtents(self._atspi.DESKTOP_COORDS)
            if extents.width <= 0 or extents.height <= 0:
                return None
            return {"x": extents.x, "y": extents.y, "width": extents.width, "height": extents.height}
        except Exception:
            return None

    def _state_contains(self, accessible: Any, state: Any) -> bool:
        try:
            return bool(accessible.getState().contains(state))
        except Exception:
            return False

    def _window_accessibles(self) -> list[Any]:
        desktop = self._atspi.Registry.getDesktop(0)
        results: list[Any] = []
        stack = [desktop]
        inspected = 0
        while stack and inspected < 2000 and len(results) < 100:
            accessible = stack.pop()
            inspected += 1
            role = self._role(accessible).lower()
            if role in {"frame", "window", "dialog"} and self._state_contains(accessible, self._atspi.STATE_SHOWING):
                results.append(accessible)
                continue
            try:
                count = min(int(accessible.childCount), 200)
                stack.extend(accessible.getChildAtIndex(index) for index in reversed(range(count)))
            except Exception:
                continue
        return results

    def list_windows(self) -> list[Window]:
        results: list[Window] = []
        _windows.clear()
        for index, accessible in enumerate(self._window_accessibles(), start=1):
            window_id = f"linux-{index}"
            _windows[window_id] = accessible
            process_id = None
            try:
                process_id = int(accessible.get_process_id())
            except Exception:
                pass
            results.append(Window(window_id, self._name(accessible), process_id, self._bounds(accessible)))
        return results

    def foreground_window(self) -> Window:
        windows = self.list_windows()
        active_window_ids = {
            window.window_id
            for window in windows
            if self._state_contains(_windows[window.window_id], self._atspi.STATE_ACTIVE)
        }
        return _select_active_window(windows, active_window_ids)

    def window_by_id(self, window_id: str) -> Window:
        if window_id not in _windows:
            self.list_windows()
        accessible = _windows.get(window_id)
        if accessible is None:
            raise ValueError("Unknown Linux window_id. Call list_windows and use a current ID.")
        process_id = None
        try:
            process_id = int(accessible.get_process_id())
        except Exception:
            pass
        return Window(window_id, self._name(accessible), process_id, self._bounds(accessible))

    def inspect(self, window: Window, max_nodes: int) -> tuple[list[dict[str, Any]], bool]:
        root = _windows.get(window.window_id)
        if root is None:
            root = self.window_by_id(window.window_id)
            root = _windows[window.window_id]
        pending: list[tuple[Any, str | None, int]] = [(root, None, 0)]
        nodes: list[dict[str, Any]] = []
        truncated = False

        while pending and len(nodes) < max_nodes:
            accessible, parent_id, depth = pending.pop()
            try:
                role = self._role(accessible)
                name = "" if _is_text_value_role(self.name, role) else self._name(accessible)
                element_id = cache_element(self.name, accessible, summary=_element_summary(role, name))
                action_names: list[str] = []
                try:
                    actions = accessible.queryAction()
                    action_names = [str(actions.getName(i)) for i in range(int(actions.nActions))]
                except Exception:
                    pass
                patterns = []
                if action_names:
                    patterns.append("action")
                try:
                    accessible.queryEditableText()
                    patterns.append("editable_text")
                except Exception:
                    pass
                nodes.append({
                    "element_id": element_id,
                    "parent_id": parent_id,
                    "depth": depth,
                    "role": role,
                    "name": name,
                    "automation_id": "",
                    "enabled": self._state_contains(accessible, self._atspi.STATE_ENABLED),
                    "visible": self._state_contains(accessible, self._atspi.STATE_SHOWING),
                    "focused": self._state_contains(accessible, self._atspi.STATE_FOCUSED),
                    "bounds": self._bounds(accessible),
                    "patterns": patterns,
                })
                if depth >= 12:
                    truncated = truncated or int(accessible.childCount) > 0
                    continue
                count = min(int(accessible.childCount), max_nodes)
                children = [accessible.getChildAtIndex(i) for i in range(count)]
                available = max_nodes - len(nodes) - len(pending)
                if len(children) > available:
                    truncated = True
                    children = children[:available]
                pending.extend((child, element_id, depth + 1) for child in reversed(children))
            except Exception:
                continue

        return nodes, truncated or bool(pending)

    def click(self, element_id: str) -> str:
        accessible = resolve_element(element_id, self.name)
        actions = accessible.queryAction()
        for index in range(int(actions.nActions)):
            name = str(actions.getName(index)).lower()
            if name in {"click", "press", "activate", "open"}:
                if actions.doAction(index):
                    return f"Element activated through AT-SPI action '{name}'."
        raise RuntimeError("The element exposes no supported AT-SPI activation action.")

    def set_text(self, element_id: str, text: str) -> str:
        accessible = resolve_element(element_id, self.name)
        try:
            accessible.queryEditableText().setTextContents(text)
        except Exception as error:
            raise RuntimeError("The element does not expose the AT-SPI EditableText interface.") from error
        return "Text set; AncharView did not read the value back."


def _windows_patterns(control_type: str) -> list[str]:
    patterns = []
    if control_type in {"Button", "Hyperlink", "MenuItem", "SplitButton"}:
        patterns.append("invoke")
    if control_type in {"Edit", "ComboBox"}:
        patterns.append("value")
    if control_type in {"CheckBox", "RadioButton"}:
        patterns.append("toggle")
    return patterns


def create_backend() -> DesktopBackend:
    if sys.platform == "win32":
        return WindowsBackend()
    if sys.platform.startswith("linux"):
        return LinuxBackend()
    raise RuntimeError(f"AncharView does not support {sys.platform!r}; use Windows 10+ or Linux.")
