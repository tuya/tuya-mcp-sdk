using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using TuyaMcpSdk.Example.mcp;

namespace TuyaMcpSdk.Example;

/// <summary>
/// Hosts a lightweight local MCP server using ASP.NET Core (HTTP/SSE transport).
/// Registers music and photo tools to demonstrate the bridge with Tuya gateway.
/// Mirrors examples/mcp/mock_mcp_server.py from the Python SDK.
/// </summary>
internal static class MockMcpServerHost
{
    public static Task RunAsync(int port, ILoggerFactory loggerFactory)
    {
        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.Logging.AddConsole();

        builder.Services
            .AddMcpServer()
            .WithHttpTransport()
            .WithTools<MusicTools>()
            .WithTools<PhotoTools>();

        var app = builder.Build();
        app.MapMcp();

        return app.RunAsync($"http://localhost:{port}");
    }
}
