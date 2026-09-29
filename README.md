# AncharView

AncharView is a Windows MCP server that gives desktop agents a structured view of the UI and lets them act on accessible controls. It uses Windows UI Automation first; screenshot capture remains available as a visual fallback.

## Features

- `list_windows`: enumerate visible top-level windows.
- `inspect_screen`: return a bounded UI Automation tree for a window or the foreground window. Each node includes an `element_id`, accessible name, role, bounds, and supported interaction patterns.
- `click_element`: activate a node from an inspection result through UI Automation, falling back to the provider's clickable point.
- `set_text`: set an editable control through its UI Automation Value pattern.
- `capture_screen`: return the virtual desktop as a PNG image for visual-only content.

The server does not continuously capture or upload the desktop. Tools run only when called by the connected MCP client. Text values are not read back, element traversal is bounded, and unsupported text controls fail rather than using simulated typing.

## Requirements

- Windows 10 or later
- .NET 10 SDK
- An MCP client that supports stdio servers

## Run

```powershell
dotnet run --project src/AncharView.Server/AncharView.Server.csproj
```

The server uses stdio for MCP messages; diagnostics are written to stderr. A VS Code MCP configuration is included in `.vscode/mcp.json`.

## Limitations

UI Automation quality depends on each application's accessibility provider. Canvas-based, remote-desktop, elevated, and custom-rendered interfaces may expose little or no semantic structure; use `capture_screen` for those cases. AncharView must run in the same Windows user session as the desktop. Windows security boundaries can prevent interaction with elevated applications.

The `element_id` values are process-local and intended for a recent inspection result. Inspect again after the UI changes.
