# AncharView project guidance

- This is a Windows-only MCP stdio server built with the official C# SDK: https://github.com/modelcontextprotocol/csharp-sdk
- Keep stdout reserved for MCP protocol traffic. Send diagnostics to stderr through `Microsoft.Extensions.Logging`.
- Prefer Windows UI Automation structure and control patterns over coordinate actions. Keep tree traversal bounded and element IDs short-lived.
- Do not read back text field values or capture the desktop automatically. Keep screenshot capture an explicit fallback tool.
- Preserve the Windows user-session boundary and document UI Automation provider limitations.