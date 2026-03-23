# Custom MCP SDK

## 1. 概述

### 1.1. SDK 使用方式

- 初始化 SDK 配置
> 初始化前，需要先从涂鸦开发者平台获取 AccessId、AccessSecret 和 Endpoint。

```csharp
using Tuya.McpSdk;

var client = new TuyaMcpClient(new TuyaMcpOptions
{
    // 设置 Access ID、Access Secret 和 Endpoint
    Endpoint                = "https://openapi.tuyaeu.com",
    AccessId                = "<your-access-id>",
    AccessSecret            = "<your-access-secret>",
    // 设置自定义 MCP 服务器地址
    CustomMcpServerEndpoint = "http://localhost:8080",
});
```

- 启动 SDK

```csharp
await client.StartAsync();   // 后台启动重连循环，立即返回
```

### 1.2. 架构图

```
  涂鸦 IoT 云
  (gateway ws/mcp)
       │  WebSocket（二进制 JSON 帧，HMAC-SHA256 签名）
       ▼
  TuyaMcpClient  ←── TuyaMcpOptions
       │
       ├── TuyaAuthService  (GET /v1/client/registration)
       ├── TuyaMcpSession   (ClientWebSocket，指数退避重连)
       └── TuyaMcpHandler   (tools/list, tools/call, root/kickout, root/migrate)
                │  HTTP（SSE / StreamableHttp，自动协商）
                ▼
  本地 MCP 服务器（你的自定义工具）
```

## 2. 快速开始

**前置条件：**

> 已安装 .NET 10 SDK。下载地址：https://dotnet.microsoft.com/download

1. 克隆仓库

    ```shell
    git clone https://github.com/tuya/tuya-mcp-sdk.git
    cd mcp-csharp
    ```

2. 配置凭证

    推荐使用 [.NET 用户机密](https://learn.microsoft.com/zh-cn/aspnet/core/security/app-secrets)（不会将密钥写入源码）：

    ```shell
    cd examples/TuyaMcpSdk.Example
    dotnet user-secrets set "Tuya:AccessId"     "<your-access-id>"
    dotnet user-secrets set "Tuya:AccessSecret" "<your-access-secret>"
    dotnet user-secrets set "Tuya:Endpoint"     "https://openapi.tuyaeu.com"
    ```

    也可以直接编辑 `examples/TuyaMcpSdk.Example/appsettings.json`。配置优先级从低到高为：

    | 来源 | 示例 |
    |------|------|
    | `appsettings.json` | 基础默认值 |
    | `appsettings.{env}.json` | 环境特定覆盖 |
    | 用户机密 | `dotnet user-secrets set ...` |
    | 环境变量 | `Tuya__AccessId=xxx` |
    | 命令行参数 | `--Tuya:AccessId xxx` |

3. 运行示例

    ```shell
    dotnet run --project examples/TuyaMcpSdk.Example
    ```

    预期输出：

    ```
    info: Main[0]  Starting local MCP server on http://localhost:8080
    info: Main[0]  Starting Tuya MCP Client...
    info: Tuya.McpSdk.TuyaMcpClient[0]  Registered successfully. client_id=…
    info: Tuya.McpSdk.TuyaMcpClient[0]  WebSocket connected
    info: Main[0]  Tuya MCP Client started. Press Ctrl+C to exit.
    ```

## 3. 开发自定义 MCP 服务器

> 开发者根据业务需要自定义 MCP 服务器，将设备能力封装为 MCP 工具。

### 3.1. 使用 [ModelContextProtocol.AspNetCore](https://www.nuget.org/packages/ModelContextProtocol.AspNetCore) 开发

- 创建 MCP 服务器

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

- 定义工具

```csharp
using System.ComponentModel;
using ModelContextProtocol.Server;

[McpServerToolType]
public sealed class MyTools
{
    [McpServerTool, Description("向某人打招呼")]
    public static string Hello(
        [Description("要打招呼的人的名字")] string name)
        => $"Hello, {name}!";
}
```

完整示例请参考 [examples/TuyaMcpSdk.Example/mcp/](examples/TuyaMcpSdk.Example/mcp/)，其中包含 `MusicTools` 和 `PhotoTools`。

### 3.2. 与 TuyaMcpClient 集成

```csharp
await using var client = new TuyaMcpClient(
    new TuyaMcpOptions
    {
        Endpoint                = "https://openapi.tuyaeu.com",
        AccessId                = "<your-access-id>",
        AccessSecret            = "<your-access-secret>",
        CustomMcpServerEndpoint = "http://localhost:8080",   // 上面启动的 MCP 服务器
    },
    loggerFactory);

await client.StartAsync();
```

## 4. 配置参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `Endpoint` | *(必填)* | 涂鸦 REST + WebSocket 基础地址，如 `https://openapi.tuyaeu.com` |
| `AccessId` | *(必填)* | 涂鸦 IoT 控制台的 Access ID |
| `AccessSecret` | *(必填)* | 涂鸦 IoT 控制台的 Access Secret |
| `CustomMcpServerEndpoint` | *(必填)* | 本地 MCP 服务器地址（无需路径后缀） |
| `InitialReconnectDelaySeconds` | `1` | 连接失败后的初始退避延迟（秒） |
| `MaxReconnectDelaySeconds` | `120` | 最大退避延迟（秒） |
| `ReceiveLoopDelay` | `20ms` | 每帧处理完成后的暂停时间，高消息频率时用于限制 CPU 占用 |

## 5. 项目结构

```
mcp-csharp/
├── TuyaMcpSdk.slnx                          ← 解决方案文件
├── src/
│   └── Tuya.McpSdk/
│       ├── TuyaMcpClient.cs                 ← 公开入口
│       ├── TuyaMcpOptions.cs                ← 配置
│       ├── Auth/
│       │   └── TuyaAuthService.cs           ← 注册 + WebSocket 头部签名
│       ├── Mcp/
│       │   ├── TuyaMcpHandler.cs            ← 消息分发
│       │   └── TuyaMcpSession.cs            ← WebSocket 生命周期 + 接收循环
│       ├── Protocol/
│       │   └── TuyaEnvelope.cs              ← 协议模型（请求、响应、鉴权）
│       └── Security/
│           └── TuyaSigning.cs               ← HMAC-SHA256 工具方法
└── examples/
    └── TuyaMcpSdk.Example/
        ├── Program.cs                       ← 入口程序
        ├── MockMcpServerHost.cs             ← 本地 ASP.NET Core MCP 服务器
        ├── appsettings.json                 ← 配置模板
        └── mcp/
            ├── MusicTools.cs                ← play_music / stop_music 工具
            └── PhotoTools.cs                ← take_photo / view_photo 工具
```

## 6. 协议说明

- **注册**：携带 HMAC-SHA256 签名头部调用 `GET /v1/client/registration`，返回 `token` + `client_id`。
- **WebSocket URL**：由 `Endpoint` 自动推导（http→ws，https→wss），格式为 `wss://…/ws/mcp?client_id=…`。
- **帧签名**：将字段按 key 排序（排除 `sign`），拼接为 `key:value\n`，使用 auth token 作为 HMAC-SHA256 密钥。
- **HTTP 签名**：格式为 `access_id\nt\nHMAC-SHA256\nnonce\n\n\n\n{path}`，使用 access secret 作为 HMAC-SHA256 密钥。

## 7. 环境要求

- .NET 10.0+
- [`ModelContextProtocol` 1.1.0](https://www.nuget.org/packages/ModelContextProtocol)（通过 NuGet 自动还原）
- [`ModelContextProtocol.AspNetCore` 1.1.0](https://www.nuget.org/packages/ModelContextProtocol.AspNetCore)（仅示例项目需要）
