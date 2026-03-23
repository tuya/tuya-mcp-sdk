using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using Tuya.McpSdk.Protocol;
using Tuya.McpSdk.Security;

namespace Tuya.McpSdk.Mcp;

/// <summary>
/// Handles individual WebSocket message frames received from the Tuya gateway.
/// Mirrors handler.go (MCPSdkHandler) in the Go SDK.
///
/// For every tools/list or tools/call request the handler creates a short-lived
/// <see cref="McpClient"/> against the downstream (local) MCP server, executes
/// the call, and sends the signed response back through the session.
/// </summary>
internal sealed class TuyaMcpHandler
{
    private readonly TuyaMcpOptions _options;
    private readonly TuyaMcpSession _session;
    private readonly ILogger        _logger;

    // Raised by the handler when the gateway sends root/kickout or root/migrate.
    public event Func<Task>? KickoutRequested;
    public event Func<Task>? MigrateRequested;

    public TuyaMcpHandler(TuyaMcpOptions options, TuyaMcpSession session, ILogger logger)
    {
        _options = options;
        _session = session;
        _logger  = logger;
    }

    // ─── Entry point ─────────────────────────────────────────────────────────

    /// <summary>
    /// Decodes, verifies, and dispatches an inbound binary frame.
    /// Mirrors MCPSdkHandler.HandleMessageBinary in Go.
    /// </summary>
    public async Task HandleFrameAsync(byte[] frame, string token)
    {
        TuyaRequest? req;
        try
        {
            req = TuyaEnvelopeJson.Deserialize<TuyaRequest>(Encoding.UTF8.GetString(frame));
        }
        catch (JsonException ex)
        {
            _logger.LogError(ex, "Failed to deserialise inbound frame");
            return;
        }

        if (req is null)
        {
            _logger.LogWarning("Received null frame");
            return;
        }

        _logger.LogDebug("Received frame method={Method} request_id={Id}", req.Method, req.RequestId);

        // Verify signature
        if (!TuyaSigning.VerifyWsFrame(RequestFields(req), token, req.Sign))
        {
            _logger.LogError("Signature verification failed for request_id={Id}", req.RequestId);
            return;
        }

        switch (req.Method)
        {
            case "tools/list":
                await HandleToolsListAsync(req, token).ConfigureAwait(false);
                break;

            case "tools/call":
                await HandleToolsCallAsync(req, token).ConfigureAwait(false);
                break;

            case "root/kickout":
                _logger.LogInformation("Received kickout from gateway");
                if (KickoutRequested is not null) await KickoutRequested.Invoke().ConfigureAwait(false);
                break;

            case "root/migrate":
                _logger.LogInformation("Received migrate from gateway");
                if (MigrateRequested is not null) await MigrateRequested.Invoke().ConfigureAwait(false);
                break;

            default:
                _logger.LogWarning("Unknown method: {Method}", req.Method);
                break;
        }
    }

    // ─── tools/list ──────────────────────────────────────────────────────────

    private async Task HandleToolsListAsync(TuyaRequest req, string token)
    {
        try
        {
            await using var mcpClient = await CreateMcpClientAsync().ConfigureAwait(false);
            var tools = await mcpClient.ListToolsAsync(cancellationToken: CancellationToken.None)
                                       .ConfigureAwait(false);

            var listResult = new ListToolsResult { Tools = tools.Select(t => t.ProtocolTool).ToList() };
            var resultJson = JsonSerializer.Serialize(listResult, McpJsonUtilities.DefaultOptions);

            await ReplyAsync(req, resultJson, token).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "tools/list failed");
            await ReplyErrorAsync(req, ex.Message, token).ConfigureAwait(false);
        }
    }

    // ─── tools/call ──────────────────────────────────────────────────────────

    private async Task HandleToolsCallAsync(TuyaRequest req, string token)
    {
        // Parse the inner "request" JSON to extract tool name + arguments
        string? toolName;
        IReadOnlyDictionary<string, object?>? toolArgs;

        try
        {
            var node = JsonNode.Parse(req.Request);
            toolName = node?["params"]?["name"]?.GetValue<string>();
            var argsNode = node?["params"]?["arguments"];
            toolArgs = argsNode is not null
                ? argsNode.AsObject().ToDictionary(
                    kv => kv.Key,
                    kv => (object?)kv.Value?.DeepClone())
                : null;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to parse tools/call request body");
            await ReplyErrorAsync(req, "invalid request body", token).ConfigureAwait(false);
            return;
        }

        if (string.IsNullOrEmpty(toolName))
        {
            await ReplyErrorAsync(req, "missing params.name in tools/call request", token).ConfigureAwait(false);
            return;
        }

        try
        {
            await using var mcpClient = await CreateMcpClientAsync().ConfigureAwait(false);
            var result = await mcpClient.CallToolAsync(
                toolName,
                toolArgs,
                cancellationToken: CancellationToken.None).ConfigureAwait(false);

            var resultJson = JsonSerializer.Serialize(result, McpJsonUtilities.DefaultOptions);
            await ReplyAsync(req, resultJson, token).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "tools/call failed for tool {Tool}", toolName);
            await ReplyErrorAsync(req, ex.Message, token).ConfigureAwait(false);
        }
    }

    // ─── Response helpers ────────────────────────────────────────────────────

    private async Task ReplyAsync(TuyaRequest req, string responseJson, string token)
    {
        var resp = new TuyaResponse
        {
            RequestId = req.RequestId,
            Endpoint  = req.Endpoint,
            Version   = req.Version,
            Method    = req.Method,
            Ts        = req.Ts,
            Response  = responseJson,
        };

        var sign = TuyaSigning.SignWsFrame(ResponseFields(resp), token);
        resp = resp with { Sign = sign };

        var json = TuyaEnvelopeJson.Serialize(resp);
        _logger.LogDebug("Sending response request_id={Id}", resp.RequestId);
        await _session.SendAsync(json).ConfigureAwait(false);
    }

    private async Task ReplyErrorAsync(TuyaRequest req, string message, string token)
    {
        var errorResult = new CallToolResult
        {
            Content = [new TextContentBlock { Text = message }],
            IsError = true,
        };
        var errorJson = JsonSerializer.Serialize(errorResult, McpJsonUtilities.DefaultOptions);
        await ReplyAsync(req, errorJson, token).ConfigureAwait(false);
    }

    // ─── MCP client factory ──────────────────────────────────────────────────

    /// <summary>
    /// Creates a short-lived <see cref="McpClient"/> connecting to the downstream
    /// local MCP server endpoint via HTTP transport (SSE or StreamableHttp auto-detected).
    /// Caller must dispose the returned client.
    /// </summary>
    private async Task<McpClient> CreateMcpClientAsync()
    {
        var transport = new HttpClientTransport(new HttpClientTransportOptions
        {
            Endpoint = new Uri(_options.CustomMcpServerEndpoint),
        });
        return await McpClient.CreateAsync(transport).ConfigureAwait(false);
    }

    // ─── Signing field helpers ────────────────────────────────────────────────

    private static IReadOnlyDictionary<string, string> RequestFields(TuyaRequest r) =>
        new Dictionary<string, string>
        {
            ["request_id"] = r.RequestId,
            ["endpoint"]   = r.Endpoint,
            ["version"]    = r.Version,
            ["method"]     = r.Method,
            ["ts"]         = r.Ts,
            ["request"]    = r.Request,
        };

    private static IReadOnlyDictionary<string, string> ResponseFields(TuyaResponse r) =>
        new Dictionary<string, string>
        {
            ["request_id"] = r.RequestId,
            ["endpoint"]   = r.Endpoint,
            ["version"]    = r.Version,
            ["method"]     = r.Method,
            ["ts"]         = r.Ts,
            ["response"]   = r.Response,
        };
}
