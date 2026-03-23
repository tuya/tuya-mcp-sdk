namespace Tuya.McpSdk;

/// <summary>
/// Configuration options for <see cref="TuyaMcpClient"/>.
/// Mirrors the Config struct in the Go SDK and the config.yaml used by the Go/Python examples.
/// </summary>
public sealed class TuyaMcpOptions
{
    /// <summary>
    /// Tuya IoT platform base endpoint, e.g. "https://openapi.tuyaeu.com".
    /// The SDK will derive the registration URL (/v1/client/registration) and
    /// the WebSocket URL (wss://…/ws/mcp) automatically.
    /// </summary>
    public required string Endpoint { get; init; }

    /// <summary>Access ID (also called access_key) from the Tuya IoT console.</summary>
    public required string AccessId { get; init; }

    /// <summary>Access Secret from the Tuya IoT console.</summary>
    public required string AccessSecret { get; init; }

    /// <summary>
    /// URL of the downstream (local) MCP server that handles tools/list and tools/call.
    /// Example: "http://localhost:8080" (no path suffix required; the transport auto-negotiates).
    /// </summary>
    public required string CustomMcpServerEndpoint { get; init; }

    /// <summary>Initial reconnect delay in seconds (exponential backoff base). Default 1.</summary>
    public int InitialReconnectDelaySeconds { get; init; } = 1;

    /// <summary>Maximum reconnect delay in seconds. Default 120.</summary>
    public int MaxReconnectDelaySeconds { get; init; } = 120;

    /// <summary>
    /// Optional pause after each received WebSocket frame before looping back to the next receive.
    /// Useful for throttling CPU in high-frequency scenarios. Default 20 ms.
    /// </summary>
    public TimeSpan ReceiveLoopDelay { get; init; } = TimeSpan.FromMilliseconds(20);
}
