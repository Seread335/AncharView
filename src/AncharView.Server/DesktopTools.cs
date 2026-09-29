using System.Collections.Concurrent;
using System.ComponentModel;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Text.Json;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Server;
using System.Windows.Automation;
using System.Windows.Forms;

namespace AncharView.Server;

[McpServerToolType]
public sealed class DesktopTools
{
    private const int DefaultNodeLimit = 300;
    private const int MaximumNodeLimit = 1200;
    private const int MaximumCachedElements = 10000;
    private static readonly TimeSpan ElementLifetime = TimeSpan.FromMinutes(2);
    private static readonly ConcurrentDictionary<string, CachedElement> ElementCache = new();
    private static long _nextElementId;

    [McpServerTool, Description("List visible top-level windows. Use window_id with inspect_screen to inspect one window.")]
    public static string ListWindows()
    {
        var windows = AutomationElement.RootElement.FindAll(
            TreeScope.Children,
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Window));

        var results = new List<object>();
        foreach (AutomationElement window in windows)
        {
            try
            {
                var current = window.Current;
                if (current.IsOffscreen || current.NativeWindowHandle == 0)
                {
                    continue;
                }

                results.Add(new
                {
                    window_id = FormatWindowId(current.NativeWindowHandle),
                    title = current.Name,
                    process_id = current.ProcessId,
                    enabled = current.IsEnabled
                });
            }
            catch (ElementNotAvailableException)
            {
            }
        }

        return JsonSerializer.Serialize(results);
    }

    [McpServerTool, Description("Read a bounded, structured UI Automation tree for a window. With no window_id, inspect the foreground window. Element IDs can be used by click_element and set_text.")]
    public static string InspectScreen(
        [Description("Optional window handle from list_windows, formatted as 0x... . Defaults to the foreground window.")] string? window_id = null,
        [Description("Maximum number of UI elements to return (1-1200). Defaults to 300.")] int max_nodes = DefaultNodeLimit)
    {
        var handle = window_id is null ? GetForegroundWindow() : ParseWindowId(window_id);
        if (handle == 0)
        {
            throw new InvalidOperationException("No foreground window is available.");
        }

        var root = AutomationElement.FromHandle(handle);
        var nodeLimit = Math.Clamp(max_nodes, 1, MaximumNodeLimit);
        var nodes = new List<object>(Math.Min(nodeLimit, 256));
        var pending = new Stack<(AutomationElement Element, int Depth)>();
        var truncated = false;
        pending.Push((root, 0));

        while (pending.Count > 0 && nodes.Count < nodeLimit)
        {
            var (element, depth) = pending.Pop();
            try
            {
                var current = element.Current;
                var id = AddToCache(element);
                var bounds = current.BoundingRectangle;
                var patterns = GetPatterns(element);

                nodes.Add(new
                {
                    element_id = id,
                    depth,
                    role = current.ControlType.ProgrammaticName,
                    name = current.Name,
                    automation_id = current.AutomationId,
                    enabled = current.IsEnabled,
                    offscreen = current.IsOffscreen,
                    bounds = bounds.IsEmpty ? null : new
                    {
                        x = bounds.X,
                        y = bounds.Y,
                        width = bounds.Width,
                        height = bounds.Height
                    },
                    patterns
                });

                if (depth >= 12)
                {
                    truncated |= TreeWalker.ControlViewWalker.GetFirstChild(element) is not null;
                    continue;
                }

                var children = new List<AutomationElement>();
                var queueLimit = nodeLimit - nodes.Count;
                for (var child = TreeWalker.ControlViewWalker.GetFirstChild(element);
                     child is not null;
                     child = TreeWalker.ControlViewWalker.GetNextSibling(child))
                {
                    if (pending.Count + children.Count >= queueLimit)
                    {
                        truncated = true;
                        break;
                    }

                    children.Add(child);
                }

                for (var index = children.Count - 1; index >= 0; index--)
                {
                    pending.Push((children[index], depth + 1));
                }
            }
            catch (ElementNotAvailableException)
            {
            }
        }

        return JsonSerializer.Serialize(new
        {
            window_id = FormatWindowId(handle.ToInt32()),
            truncated = truncated || pending.Count > 0,
            node_count = nodes.Count,
            nodes
        });
    }

    [McpServerTool, Description("Activate an element returned by inspect_screen using its element_id. Uses UI Automation patterns first, then a provider-reported clickable point.")]
    public static string ClickElement(
        [Description("element_id from the latest inspect_screen result.")] string element_id)
    {
        var element = GetCachedElement(element_id);
        if (!element.Current.IsEnabled)
        {
            throw new InvalidOperationException("The requested element is disabled.");
        }

        if (element.TryGetCurrentPattern(InvokePattern.Pattern, out var invokePattern))
        {
            ((InvokePattern)invokePattern).Invoke();
            return "Element invoked.";
        }

        if (element.TryGetCurrentPattern(TogglePattern.Pattern, out var togglePattern))
        {
            ((TogglePattern)togglePattern).Toggle();
            return "Element toggled.";
        }

        if (element.TryGetClickablePoint(out var point))
        {
            if (!SetCursorPos((int)point.X, (int)point.Y))
            {
                throw new InvalidOperationException("Windows could not move the pointer to the element.");
            }

            MouseEvent(MouseEventLeftDown, 0, 0, 0, UIntPtr.Zero);
            MouseEvent(MouseEventLeftUp, 0, 0, 0, UIntPtr.Zero);
            return "Element clicked at its UI Automation clickable point.";
        }

        throw new InvalidOperationException("The element exposes no supported activation pattern or clickable point.");
    }

    [McpServerTool, Description("Set text on an element returned by inspect_screen through its UI Automation Value pattern. The current value is never returned by AncharView.")]
    public static string SetText(
        [Description("element_id from the latest inspect_screen result.")] string element_id,
        [Description("Text to set in the target control.")] string text)
    {
        var element = GetCachedElement(element_id);
        if (!element.Current.IsEnabled)
        {
            throw new InvalidOperationException("The requested element is disabled.");
        }

        if (!element.TryGetCurrentPattern(ValuePattern.Pattern, out var valuePattern))
        {
            throw new InvalidOperationException("The element does not expose a UI Automation Value pattern; text was not entered.");
        }

        var value = (ValuePattern)valuePattern;
        if (value.Current.IsReadOnly)
        {
            throw new InvalidOperationException("The requested element is read-only.");
        }

        value.SetValue(text);
        return "Text set. The resulting value was not read back.";
    }

    [McpServerTool, Description("Capture the virtual desktop as a PNG image. Use this fallback when the UI Automation tree does not expose relevant visual content.")]
    public static IEnumerable<AIContent> CaptureScreen()
    {
        var bounds = SystemInformation.VirtualScreen;
        if (bounds.Width <= 0 || bounds.Height <= 0)
        {
            throw new InvalidOperationException("The virtual desktop has no capturable area.");
        }

        using var bitmap = new Bitmap(bounds.Width, bounds.Height);
        using (var graphics = Graphics.FromImage(bitmap))
        {
            graphics.CopyFromScreen(bounds.Left, bounds.Top, 0, 0, bounds.Size);
        }

        using var stream = new MemoryStream();
        bitmap.Save(stream, System.Drawing.Imaging.ImageFormat.Png);
        var dataUri = $"data:image/png;base64,{Convert.ToBase64String(stream.ToArray())}";
        return [new TextContent("Virtual desktop capture (PNG):"), new DataContent(dataUri)];
    }

    private static string AddToCache(AutomationElement element)
    {
        var id = $"e{Interlocked.Increment(ref _nextElementId):x}";
        ElementCache[id] = new CachedElement(element, DateTimeOffset.UtcNow);

        if (ElementCache.Count > MaximumCachedElements)
        {
            foreach (var staleId in ElementCache.Keys.Take(ElementCache.Count - MaximumCachedElements))
            {
                ElementCache.TryRemove(staleId, out _);
            }
        }

        return id;
    }

    private static AutomationElement GetCachedElement(string elementId)
    {
        if (!ElementCache.TryGetValue(elementId, out var cached))
        {
            throw new InvalidOperationException("Unknown or expired element_id. Call inspect_screen again and use an ID from its result.");
        }

        if (DateTimeOffset.UtcNow - cached.CreatedAt > ElementLifetime)
        {
            ElementCache.TryRemove(elementId, out _);
            throw new InvalidOperationException("This element_id expired. Call inspect_screen again and use a fresh ID.");
        }

        return cached.Element;
    }

    private static string[] GetPatterns(AutomationElement element)
    {
        var supported = new List<string>(4);
        if (element.TryGetCurrentPattern(InvokePattern.Pattern, out _)) supported.Add("invoke");
        if (element.TryGetCurrentPattern(ValuePattern.Pattern, out _)) supported.Add("value");
        if (element.TryGetCurrentPattern(TogglePattern.Pattern, out _)) supported.Add("toggle");
        if (element.TryGetCurrentPattern(SelectionItemPattern.Pattern, out _)) supported.Add("select");
        return [.. supported];
    }

    private static IntPtr ParseWindowId(string windowId)
    {
        var value = windowId.StartsWith("0x", StringComparison.OrdinalIgnoreCase)
            ? windowId[2..]
            : windowId;
        return new IntPtr(int.Parse(value, NumberStyles.HexNumber, CultureInfo.InvariantCulture));
    }

    private static string FormatWindowId(int handle) => $"0x{handle:x}";

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [System.Runtime.InteropServices.DllImport("user32.dll", SetLastError = true)]
    [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
    private static extern bool SetCursorPos(int x, int y);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern void MouseEvent(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);

    private const uint MouseEventLeftDown = 0x0002;
    private const uint MouseEventLeftUp = 0x0004;

    private sealed record CachedElement(AutomationElement Element, DateTimeOffset CreatedAt);
}