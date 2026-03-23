using System.Net.WebSockets;
using System.Text;
using Microsoft.Extensions.Logging;
using Tuya.McpSdk.Auth;

namespace Tuya.McpSdk.Mcp;

/// <summary>
/// Manages the WebSocket connection to the Tuya MCP gateway and exposes an
/// outbound message channel.  Mirrors session.go + the reconnect loop in sdk.go.
/// </summary>
internal sealed class TuyaMcpSession : IAsyncDisposable
{
    private readonly TuyaMcpOptions  _options;
    private readonly TuyaAuthService _auth;
    private readonly ILogger         _logger;

    private ClientWebSocket?      _ws;
    private CancellationTokenSource? _sessionCts;

    // ─── Events ──────────────────────────────────────────────────────────────

    /// <summary>Raised when a binary frame is received from the gateway.</summary>
    public event Func<byte[], Task>? MessageReceived;

    /// <summary>Raised when the connection is cleanly established.</summary>
    public event Func<Task>? Connected;

    /// <summary>Raised when the connection is lost (before reconnect attempt).</summary>
    public event Func<Task>? Disconnected;

    public TuyaMcpSession(TuyaMcpOptions options, TuyaAuthService auth, ILogger logger)
    {
        _options = options;
        _auth    = auth;
        _logger  = logger;
    }

    // ─── Connect ─────────────────────────────────────────────────────────────

    /// <summary>
    /// Establishes the WebSocket connection (after auth) and starts the receive loop.
    /// Throws if connection fails; the caller (<see cref="TuyaMcpClient"/>) handles
    /// retry with exponential back-off.
    /// </summary>
    public async Task ConnectAsync(CancellationToken ct)
    {
        await CloseCurrentAsync().ConfigureAwait(false);

        var (wsUri, headers) = _auth.BuildWsConnectParams();

        _ws = new ClientWebSocket();
        foreach (var (key, value) in headers)
            _ws.Options.SetRequestHeader(key, value);

        _logger.LogInformation("WebSocket connecting to {Uri}", wsUri);
        await _ws.ConnectAsync(wsUri, ct).ConfigureAwait(false);
        _logger.LogInformation("WebSocket connected");

        _sessionCts = CancellationTokenSource.CreateLinkedTokenSource(ct);

        if (Connected is not null)
            await Connected.Invoke().ConfigureAwait(false);

        _ = Task.Run(() => ReceiveLoopAsync(_sessionCts.Token), _sessionCts.Token);
    }

    // ─── Send ─────────────────────────────────────────────────────────────────

    /// <summary>Sends a binary frame (UTF-8 encoded JSON) to the gateway. Thread-safe.</summary>
    public async Task SendAsync(string json, CancellationToken ct = default)
    {
        if (_ws is null || _ws.State != WebSocketState.Open)
        {
            _logger.LogWarning("Cannot send: WebSocket is not open");
            return;
        }

        var bytes = Encoding.UTF8.GetBytes(json);
        await _ws.SendAsync(bytes, WebSocketMessageType.Binary, true, ct).ConfigureAwait(false);
    }

    // ─── Receive loop ─────────────────────────────────────────────────────────

    private async Task ReceiveLoopAsync(CancellationToken ct)
    {
        var buffer = new byte[64 * 1024];

        try
        {
            while (!ct.IsCancellationRequested && _ws?.State == WebSocketState.Open)
            {
                using var ms = new MemoryStream();
                WebSocketReceiveResult result;
                var closed = false;

                do
                {
                    result = await _ws.ReceiveAsync(buffer, ct).ConfigureAwait(false);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        _logger.LogInformation("WebSocket close frame received");
                        await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", ct).ConfigureAwait(false);
                        closed = true;
                        break;
                    }
                    ms.Write(buffer, 0, result.Count);
                }
                while (!result.EndOfMessage);

                if (closed) break;

                var frame = ms.ToArray();
                if (frame.Length > 0 && MessageReceived is not null)
                    await MessageReceived.Invoke(frame).ConfigureAwait(false);

                // honour the configured receive-loop delay
                if (_options.ReceiveLoopDelay > TimeSpan.Zero)
                    await Task.Delay(_options.ReceiveLoopDelay, ct).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) { /* expected on shutdown */ }
        catch (WebSocketException ex)
        {
            _logger.LogWarning(ex, "WebSocket error in receive loop");
        }

        _logger.LogInformation("WebSocket receive loop ended");
        if (Disconnected is not null)
            await Disconnected.Invoke().ConfigureAwait(false);
    }

    // ─── Disconnect ───────────────────────────────────────────────────────────

    private async Task CloseCurrentAsync()
    {
        if (_sessionCts is not null)
        {
            await _sessionCts.CancelAsync().ConfigureAwait(false);
            _sessionCts.Dispose();
            _sessionCts = null;
        }

        if (_ws is not null)
        {
            try
            {
                if (_ws.State == WebSocketState.Open)
                    await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "reconnect", CancellationToken.None)
                             .ConfigureAwait(false);
            }
            catch { /* best-effort */ }
            _ws.Dispose();
            _ws = null;
        }
    }

    public async ValueTask DisposeAsync()
    {
        await CloseCurrentAsync().ConfigureAwait(false);
    }
}
