# Custom MCP SDK

## 1. Overview

### 1.1. SDK Usage

- Init SDK Config
> Before initialization, you need to obtain AccessId, AccessSecret, and Endpoint from the Tuya developer platform.

```csharp
using Tuya.McpSdk;

var client = new TuyaMcpClient(new TuyaMcpOptions
{
    // Set Access ID, Access Secret and Endpoint
    Endpoint                = "https://openapi.tuyaeu.com",
    AccessId                = "<your-access-id>",
    AccessSecret            = "<your-access-secret>",
    // Set custom MCP server endpoint
    CustomMcpServerEndpoint = "http://localhost:8080",
});
```

- Running SDK

```csharp
await client.StartAsync();   // starts reconnect loop in the background
```

### 1.2. Architecture Diagram

```
  Tuya IoT Cloud
  (gateway ws/mcp)
       │  WebSocket (binary JSON frames, HMAC-SHA256 signed)
       ▼
  TuyaMcpClient  ←── TuyaMcpOptions
       │
       ├── TuyaAuthService  (GET /v1/client/registration)
       ├── TuyaMcpSession   (ClientWebSocket, exponential-backoff reconnect)
       └── TuyaMcpHandler   (tools/list, tools/call, root/kickout, root/migrate)
                │  HTTP (SSE / StreamableHttp, auto-negotiated)
                ▼
  Local MCP Server (your tools)
```

## 2. Quick Start

**Prerequisites:**

> .NET 10 SDK installed. Download from https://dotnet.microsoft.com/download

1. Clone the repository

    ```shell
    git clone https://github.com/tuya/tuya-mcp-sdk.git
    cd mcp-csharp
    ```

2. Configure credentials

    Copy `examples/TuyaMcpSdk.Example/appsettings.json` and fill in your credentials, or use [.NET User Secrets](https://learn.microsoft.com/aspnet/core/security/app-secrets) (recommended — keeps secrets out of source control):

    ```shell
    cd examples/TuyaMcpSdk.Example
    dotnet user-secrets set "Tuya:AccessId"     "<your-access-id>"
    dotnet user-secrets set "Tuya:AccessSecret" "<your-access-secret>"
    dotnet user-secrets set "Tuya:Endpoint"     "https://openapi.tuyaeu.com"
    ```

    Configuration is loaded in priority order (last wins):

    | Source | Example |
    |--------|---------|
    | `appsettings.json` | baseline defaults |
    | `appsettings.{env}.json` | environment overrides |
    | User Secrets | `dotnet user-secrets set ...` |
    | Environment variables | `Tuya__AccessId=xxx` |
    | Command-line args | `--Tuya:AccessId xxx` |

3. Run the example

    ```shell
    dotnet run --project examples/TuyaMcpSdk.Example
    ```

    Expected output:

    ```
    info: Main[0]  Starting local MCP server on http://localhost:8080
    info: Main[0]  Starting Tuya MCP Client...
    info: Tuya.McpSdk.TuyaMcpClient[0]  Registered successfully. client_id=…
    info: Tuya.McpSdk.TuyaMcpClient[0]  WebSocket connected
    info: Main[0]  Tuya MCP Client started. Press Ctrl+C to exit.
    ```

## 3. Develop Custom MCP Server

> Developers build custom MCP Servers to expose device capabilities as MCP tools.

### 3.1. Develop with [ModelContextProtocol.AspNetCore](https://www.nuget.org/packages/ModelContextProtocol.AspNetCore)

- Create a new MCP server

```csharp
var builder = WebApplication.CreateBuilder();
builder.Services
    .AddMcpServer()
    .WithHttpTransport()
    .WithTools<MyTools>();

var app = builder.Build();
app.MapMcp();
await app.RunAsync("http://localhost:8080");
```

- Define tools

```csharp
using System.ComponentModel;
using ModelContextProtocol.Server;

[McpServerToolType]
public sealed class MyTools
{
    [McpServerTool, Description("Say hello to someone")]
    public static string Hello(
        [Description("Name of the person to greet")] string name)
        => $"Hello, {name}!";
}
```

See [examples/TuyaMcpSdk.Example/mcp/](examples/TuyaMcpSdk.Example/mcp/) for a complete working example with `MusicTools` and `PhotoTools`.

### 3.2. Wire it to TuyaMcpClient

```csharp
await using var client = new TuyaMcpClient(
    new TuyaMcpOptions
    {
        Endpoint                = "https://openapi.tuyaeu.com",
        AccessId                = "<your-access-id>",
        AccessSecret            = "<your-access-secret>",
        CustomMcpServerEndpoint = "http://localhost:8080",   // your MCP server above
    },
    loggerFactory);

await client.StartAsync();
```

## 4. Configuration Reference

| Property | Default | Description |
|----------|---------|-------------|
| `Endpoint` | *(required)* | Tuya REST + WebSocket base URL, e.g. `https://openapi.tuyaeu.com` |
| `AccessId` | *(required)* | Access ID from the Tuya IoT console |
| `AccessSecret` | *(required)* | Access Secret from the Tuya IoT console |
| `CustomMcpServerEndpoint` | *(required)* | URL of the local MCP server (no path suffix needed) |
| `InitialReconnectDelaySeconds` | `1` | Initial back-off delay (seconds) after a failed connection |
| `MaxReconnectDelaySeconds` | `120` | Maximum back-off delay (seconds) |
| `ReceiveLoopDelay` | `20ms` | Pause after each received frame; throttles CPU at high message rates |

## 5. Project Layout

```
mcp-csharp/
├── TuyaMcpSdk.slnx                          ← solution file
├── src/
│   └── Tuya.McpSdk/
│       ├── TuyaMcpClient.cs                 ← public entry point
│       ├── TuyaMcpOptions.cs                ← configuration
│       ├── Auth/
│       │   └── TuyaAuthService.cs           ← registration + WS header signing
│       ├── Mcp/
│       │   ├── TuyaMcpHandler.cs            ← message dispatcher
│       │   └── TuyaMcpSession.cs            ← WebSocket lifecycle + receive loop
│       ├── Protocol/
│       │   └── TuyaEnvelope.cs              ← wire models (request, response, auth)
│       └── Security/
│           └── TuyaSigning.cs               ← HMAC-SHA256 helpers
└── examples/
    └── TuyaMcpSdk.Example/
        ├── Program.cs                       ← entry point
        ├── MockMcpServerHost.cs             ← local ASP.NET Core MCP server
        ├── appsettings.json                 ← configuration template
        └── mcp/
            ├── MusicTools.cs                ← play_music / stop_music tools
            └── PhotoTools.cs                ← take_photo / view_photo tools
```

## 6. Protocol Notes

- **Registration**: `GET /v1/client/registration` with HMAC-SHA256 signed headers → returns `token` + `client_id`.
- **WebSocket URL**: derived automatically from `Endpoint` (http→ws, https→wss) as `wss://…/ws/mcp?client_id=…`.
- **Frame signing**: sorted `key:value\n` pairs (excluding `sign`), HMAC-SHA256 keyed with the auth token.
- **HTTP signing**: `access_id\nt\nHMAC-SHA256\nnonce\n\n\n\n{path}`, HMAC-SHA256 keyed with the access secret.

## 7. Requirements

- .NET 10.0+
- [`ModelContextProtocol` 1.1.0](https://www.nuget.org/packages/ModelContextProtocol) (auto-restored via NuGet)
- [`ModelContextProtocol.AspNetCore` 1.1.0](https://www.nuget.org/packages/ModelContextProtocol.AspNetCore) (example only)
