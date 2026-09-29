# AncharView

AncharView is a cross-platform MCP server for desktop agents. It combines accessible UI structure with vision instead of replacing screenshots: agents provide a task goal, AncharView inspects the foreground window, ranks matching controls, and attaches a cropped image only when the goal is visual or accessibility data is insufficient.

## MCP tools

- `list_windows`: enumerate visible top-level windows.
- `observe_screen`: inspect the foreground window or a selected window, return a bounded accessibility tree with task relevance, and apply `visual_mode=auto|always|never`.
- `capture_screen`: explicitly return a PNG crop of the selected or foreground window.
- `click_element`: request MCP consent, then activate an element ID from a recent observation.
- `set_text`: request MCP consent, then set a text control without reading its value back.

`auto` includes vision for visual goals such as colors, layout, icons, charts, diagrams, and images, or when the accessibility tree has too little useful content. It avoids sending image tokens for ordinary controls with a useful accessibility tree. No capture runs in the background.

`observe_screen` also accepts `detail=minimal|interactive|full`: minimal keeps task matches and focus, interactive (default) keeps relevant controls and their ancestors, and full returns the bounded tree. `max_nodes` bounds both traversal and returned context. The result reports inspected and filtered node counts so the agent can request more detail when needed.

## Source layout

All application source is tracked under `src/ancharview/`:

```text
src/ancharview/
	server.py       MCP tools, task relevance, context filtering, and vision policy
	desktop.py      Windows UIA and Linux AT-SPI adapters, element actions, capture
	audit.py        Local privacy-minimal JSONL action audit
	__main__.py     Python module entry point
	__init__.py     Package metadata
tests/
	test_vision_policy.py
	test_action_safety.py
```

The old C# source was replaced during the cross-platform migration. Local `.NET` `bin/` and `obj/` folders, Python virtualenvs, bytecode, and editable-install metadata are generated artifacts, not missing source; `.gitignore` excludes them from Git.

## Platforms

- Windows 10 or later: Windows UI Automation through `pywinauto`.
- Linux: AT-SPI through the system `pyatspi` binding; install the binding and accessibility service with the distribution package manager.
- Screenshots: `mss` on Windows and X11; `grim` is used for cropped Wayland captures when installed.

On Wayland, screenshots and input may be restricted by the compositor. AT-SPI must be enabled by the desktop session. Linux accessibility support varies across GNOME, KDE, and other environments. Applications that draw their own controls may expose limited semantics; `observe_screen` then attaches an image in auto mode.

## Install

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[windows]"
```

Linux (Debian/Ubuntu with GNOME AT-SPI packages):

```bash
sudo apt install python3-gi python3-pyatspi at-spi2-core grim
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e ".[linux]"
```

Use `--system-site-packages` so the venv can see the distribution's `pyatspi` binding. For other distributions, install the equivalent AT-SPI packages.

## Run

Windows PowerShell:

```powershell
.\.venv\Scripts\python -m ancharview
```

Linux:

```bash
.venv/bin/python -m ancharview
```

The server uses MCP stdio. Its VS Code registration in `.vscode/mcp.json` uses the Windows virtualenv path; on Linux, change `command` to `${workspaceFolder}/.venv/bin/python`. Diagnostics go to stderr. A task-aware call can be as simple as `observe_screen(task_goal="click the Save button")`. For a visual task, use `task_goal="compare the chart colors"`; `auto` will include the window image alongside structured nodes.

AncharView only reads or changes the desktop when the connected agent calls a tool. It does not send screen content to a remote service itself. Element IDs are process-local and expire after two minutes.

## Action approval and audit

Every `click_element` and `set_text` call requests approval through MCP elicitation before changing the desktop. If the client does not support elicitation, cancels, or declines, AncharView blocks the action. These tools are marked destructive in MCP metadata.

Approval is mediated by the MCP client: the MCP protocol cannot prove that a human, rather than an agent/client policy, made the decision. Use a host that presents elicitation requests to the user. The consent prompt identifies the control by its accessible role/name, but deliberately omits the proposed text value; for `set_text`, approval therefore covers the target and operation, not the exact content.

AncharView writes minimal JSONL audit events to `~/.ancharview/audit.jsonl` by default. The log records timestamps, action, short-lived element ID, and request/consent/outcome status; it does not record text values, screenshots, or window titles. On POSIX systems the directory/file are restricted to the current user. On Windows the file inherits the user's profile ACL. Set `ANCHARVIEW_AUDIT_PATH` to choose another local path.

For the implementation history, design decisions, verification, and current limitations, see [BAO_CAO.md](BAO_CAO.md).

## License

AncharView is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for the full terms.
