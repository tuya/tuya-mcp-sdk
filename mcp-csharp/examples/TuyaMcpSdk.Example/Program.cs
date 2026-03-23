using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Tuya.McpSdk;
using TuyaMcpSdk.Example;

// ─── Example entry point ──────────────────────────────────────────────────────
//
// This example:
//   1. Starts a local MCP server (via ASP.NET Core, SSE transport) that exposes
//      two tools: play_music and take_photo.
//   2. Starts a TuyaMcpClient that connects to the Tuya IoT gateway, forwards
//      tools/list and tools/call requests to the local MCP server.
//
// Configuration is loaded in priority order (last wins):
//   1. appsettings.json                — baseline defaults, safe to commit (no secrets)
//   2. appsettings.{Environment}.json  — environment-specific overrides
//   3. User Secrets (Development only) — run: dotnet user-secrets set "Tuya:AccessId" "<value>"
//                                              dotnet user-secrets set "Tuya:AccessSecret" "<value>"
//   4. Environment variables           — Tuya__Endpoint / Tuya__AccessId / Tuya__AccessSecret / Tuya__McpPort
//                                        (double-underscore __ as section separator)
//   5. Command-line arguments          — --Tuya:Endpoint <value> --Tuya:AccessId <value> ...
//
// Quick start:
//   Copy appsettings.example.json → appsettings.json, fill in AccessId/AccessSecret, then:
//   dotnet run
// ─────────────────────────────────────────────────────────────────────────────

// Host.CreateApplicationBuilder automatically loads appsettings.json,
// appsettings.{env}.json, environment variables and command-line args.
// User Secrets are added explicitly so they work in all environments (not just Development).
var builder = Host.CreateApplicationBuilder(args);
builder.Configuration.AddUserSecrets<Program>(optional: true);
var config  = builder.Configuration;

var endpoint     = config["Tuya:Endpoint"]     ?? "https://openapi.tuyaeu.com";
var accessId     = config["Tuya:AccessId"]     ?? throw new InvalidOperationException(
    "Tuya:AccessId is required. Set it in appsettings.json or env var Tuya__AccessId.");
var accessSecret = config["Tuya:AccessSecret"] ?? throw new InvalidOperationException(
    "Tuya:AccessSecret is required. Set it in appsettings.json or env var Tuya__AccessSecret.");
var mcpPort      = config.GetValue<int>("Tuya:McpPort", 8080);

var loggerFactory = LoggerFactory.Create(b => b
    .AddConsole()
    .SetMinimumLevel(LogLevel.Information));

var logger = loggerFactory.CreateLogger("Main");

// ─── 1. Start the local ASP.NET Core MCP server ───────────────────────────────
logger.LogInformation("Starting local MCP server on http://localhost:{Port}", mcpPort);

var serverTask = MockMcpServerHost.RunAsync(mcpPort, loggerFactory);

// Give the server a moment to start listening
await Task.Delay(1000);

// ─── 2. Start TuyaMcpClient ────────────────────────────────────────────────────
logger.LogInformation("Starting Tuya MCP Client...");

await using var client = new TuyaMcpClient(
    new TuyaMcpOptions
    {
        Endpoint                = endpoint,
        AccessId                = accessId,
        AccessSecret            = accessSecret,
        CustomMcpServerEndpoint = $"http://localhost:{mcpPort}",
    },
    loggerFactory);

using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

await client.StartAsync(cts.Token);

logger.LogInformation("Tuya MCP Client started. Press Ctrl+C to exit.");
await Task.Delay(Timeout.Infinite, cts.Token).ContinueWith(_ => Task.CompletedTask);

await client.StopAsync();
logger.LogInformation("Stopped.");
