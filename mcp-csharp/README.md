# Tuya MCP SDK — C# (mcp-csharp)

A C# (.NET 8) implementation of the Tuya MCP SDK.  
It bridges between the **Tuya IoT platform cloud** and a **local MCP server** (e.g. an SSE endpoint at `http://localhost:8080/sse`), following the same protocol as the Go and Python SDKs in this repository.

## Architecture

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
                │  HTTP (SSE / StreamableHttp)
                ▼
  Local MCP Server (your tools)
```

## Quick start

### 1. Add a project reference

```xml
<ProjectReference Include="..\Tuya.McpSdk\Tuya.McpSdk.csproj" />
```

### 2. Configure and start

```csharp
using Tuya.McpSdk;

var client = new TuyaMcpClient(new TuyaMcpOptions
{
    Endpoint                = "https://openapi.tuyaeu.com",
    AccessId                = "<your-access-id>",
    AccessSecret            = "<your-access-secret>",
    CustomMcpServerEndpoint = "http://localhost:8080/sse",
});

await client.StartAsync();          // starts the reconnect loop in the background
Console.ReadLine();                 // keep the process alive
await client.StopAsync();
```

### 3. With dependency injection & logging

```csharp
var loggerFactory = LoggerFactory.Create(b => b.AddConsole());

await using var client = new TuyaMcpClient(
    new TuyaMcpOptions
    {
        Endpoint                = "https://openapi.tuyaeu.com",
        AccessId                = Environment.GetEnvironmentVariable("TUYA_ACCESS_ID")!,
        AccessSecret            = Environment.GetEnvironmentVariable("TUYA_ACCESS_SECRET")!,
        CustomMcpServerEndpoint = "http://localhost:8080/sse",
    },
    loggerFactory);

await client.StartAsync();
await Task.Delay(Timeout.Infinite);
```

## Configuration reference

| Property | Default | Description |
|---|---|---|
| `Endpoint` | *(required)* | Tuya REST + WebSocket base URL, e.g. `https://openapi.tuyaeu.com` |
| `AccessId` | *(required)* | Access ID from the Tuya IoT console |
| `AccessSecret` | *(required)* | Access Secret from the Tuya IoT console |
| `CustomMcpServerEndpoint` | *(required)* | URL of the local MCP server (SSE endpoint) |
| `InitialReconnectDelaySeconds` | `1` | Starting back-off delay after a failed connection |
| `MaxReconnectDelaySeconds` | `120` | Cap for the exponential back-off delay |
| `ReceiveLoopDelay` | `20ms` | Polling interval between WebSocket receive iterations |

## Project layout

```
Tuya.McpSdk/
  TuyaMcpClient.cs          ← public entry point
  TuyaMcpOptions.cs         ← configuration
  Auth/
    TuyaAuthService.cs      ← registration + WS connect-header signing
  Mcp/
    TuyaMcpHandler.cs       ← message dispatcher (tools/list, tools/call, …)
    TuyaMcpSession.cs       ← WebSocket lifecycle + receive loop
  Protocol/
    TuyaEnvelope.cs         ← wire models (TuyaRequest, TuyaResponse, auth API)
  Security/
    TuyaSigning.cs          ← HMAC-SHA256 helpers (REST + WS frame signing)
```

## Protocol notes

- **Registration**: `GET /v1/client/registration` with signed headers → returns `token` + `client_id`.
- **WebSocket URL**: derived automatically from `Endpoint` (http→ws, https→wss) as `wss://…/ws/mcp?client_id=…`.
- **Frame signing**: sorted `key:value\n` pairs (excluding `sign`), HMAC-SHA256 with the auth token.
- **HTTP signing** (registration): `access_id\nt\nHMAC-SHA256\nnonce\n\n\n\n{path}`, HMAC-SHA256 with the access secret.

## Requirements

- .NET 8.0+
- `ModelContextProtocol` 0.4.0-preview.3 (auto-restored via NuGet)
