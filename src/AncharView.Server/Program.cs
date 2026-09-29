using AncharView.Server;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

var builder = Host.CreateApplicationBuilder(args);

builder.Logging.ClearProviders();
builder.Logging.AddConsole(options =>
	options.LogToStandardErrorThreshold = LogLevel.Trace);

builder.Services
	.AddMcpServer()
	.WithStdioServerTransport()
	.WithTools<DesktopTools>();

await builder.Build().RunAsync();
