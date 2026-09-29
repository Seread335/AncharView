# AncharView project guidance

- This is a cross-platform MCP stdio server using the official Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Keep stdout reserved for MCP protocol traffic; use Python logging for diagnostics.
- Use Windows UI Automation on Windows and AT-SPI on Linux. Keep platform-specific code behind backend adapters.
- Observation must use the agent's `task_goal`, select the foreground window by default, bound tree traversal, and include cropped vision only according to `visual_mode` and accessibility coverage.
- Never capture in the background or read back text field values. Keep element IDs process-local and short-lived.
- Document Linux AT-SPI and Wayland permissions; do not silently claim unsupported input or screen capture works.