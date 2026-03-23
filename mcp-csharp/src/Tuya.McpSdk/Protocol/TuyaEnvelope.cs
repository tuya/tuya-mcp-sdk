using System.Text.Json;
using System.Text.Json.Serialization;

namespace Tuya.McpSdk.Protocol;

// ─── Wire models for WebSocket message frames (MCPSdkBaseMsg in Go entity) ─────

/// <summary>
/// Base fields shared by every Tuya MCP WebSocket message frame.
/// Field names match the Go entity.MCPSdkBaseMsg JSON tags exactly.
/// </summary>
public record TuyaMsgBase
{
    [JsonPropertyName("request_id")] public string RequestId { get; init; } = string.Empty;
    [JsonPropertyName("endpoint")]   public string Endpoint  { get; init; } = string.Empty;
    [JsonPropertyName("version")]    public string Version   { get; init; } = string.Empty;
    [JsonPropertyName("method")]     public string Method    { get; init; } = string.Empty;
    [JsonPropertyName("ts")]         public string Ts        { get; init; } = string.Empty;
    [JsonPropertyName("sign")]       public string Sign      { get; init; } = string.Empty;
}

/// <summary>
/// Inbound request frame sent by the Tuya gateway (tools/list, tools/call, root/migrate, …).
/// Mirrors entity.MCPSdkRequest.
/// </summary>
public sealed record TuyaRequest : TuyaMsgBase
{
    [JsonPropertyName("request")] public string Request { get; init; } = string.Empty;
}

/// <summary>
/// Outbound response frame that the SDK sends back to the Tuya gateway.
/// Mirrors entity.MCPSdkResponse.
/// </summary>
public sealed record TuyaResponse : TuyaMsgBase
{
    [JsonPropertyName("response")] public string Response { get; init; } = string.Empty;
}

// ─── REST auth API models ────────────────────────────────────────────────────

/// <summary>Top-level JSON envelope returned by GET /v1/client/registration.</summary>
public sealed class TuyaAuthApiResponse
{
    [JsonPropertyName("success")] public bool       Success { get; init; }
    [JsonPropertyName("data")]    public TuyaAuthData? Data  { get; init; }
}

/// <summary>The "data" object inside the auth API response.</summary>
public sealed class TuyaAuthData
{
    [JsonPropertyName("token")]     public string Token    { get; init; } = string.Empty;
    [JsonPropertyName("client_id")] public string ClientId { get; init; } = string.Empty;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

internal static class TuyaEnvelopeJson
{
    private static readonly JsonSerializerOptions _opts = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public static string Serialize<T>(T value) =>
        JsonSerializer.Serialize(value, _opts);

    public static T? Deserialize<T>(string json) =>
        JsonSerializer.Deserialize<T>(json, _opts);
}
