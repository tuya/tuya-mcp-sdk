using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Tuya.McpSdk.Auth;
using Tuya.McpSdk.Mcp;

namespace Tuya.McpSdk;

/// <summary>
/// Top-level entry point for the Tuya MCP SDK.
/// Creates and wires together auth, WebSocket session, and message handler,
/// then runs a reconnect loop with exponential back-off.
///
/// Mirrors MCPSdk (sdk.go) and mcp_sdk.py in the Go / Python SDKs.
///
/// Usage:
/// <code>
/// var client = new TuyaMcpClient(new TuyaMcpOptions {
///     Endpoint                = "https://openapi.tuyaeu.com",
///     AccessId                = "…",
///     AccessSecret            = "…",
///     CustomMcpServerEndpoint = "http://localhost:8080",
/// });
/// await client.StartAsync();   // returns immediately; reconnect loop runs in background
/// </code>
/// </summary>
public sealed class TuyaMcpClient : IAsyncDisposable
{
    private readonly TuyaMcpOptions   _options;
    private readonly ILogger<TuyaMcpClient> _logger;
    private readonly HttpClient       _httpClient;

    private TuyaMcpSession?  _session;
    private TuyaAuthService? _auth;

    private CancellationTokenSource? _runCts;
    private bool _running;

    public TuyaMcpClient(TuyaMcpOptions options, ILoggerFactory? loggerFactory = null)
    {
        _options    = options;
        _logger     = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<TuyaMcpClient>();
        _httpClient = new HttpClient();
    }

    // ─── Public API ──────────────────────────────────────────────────────────

    /// <summary>
    /// Starts the SDK: registers with the Tuya gateway, connects the WebSocket,
    /// and enters the receive/reconnect loop.  Returns as soon as the loop is
    /// running in the background.
    /// </summary>
    public Task StartAsync(CancellationToken ct = default)
    {
        if (_running) return Task.CompletedTask;
        _running = true;

        _runCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        _auth   = new TuyaAuthService(_options, _httpClient, _logger);

        _ = Task.Run(() => RunWithReconnectAsync(_runCts.Token), _runCts.Token);
        return Task.CompletedTask;
    }

    /// <summary>Stops the SDK gracefully.</summary>
    public async Task StopAsync()
    {
        if (_runCts is not null)
            await _runCts.CancelAsync().ConfigureAwait(false);

        if (_session is not null)
            await _session.DisposeAsync().ConfigureAwait(false);

        _running = false;
    }

    // ─── Reconnect loop ───────────────────────────────────────────────────────

    private async Task RunWithReconnectAsync(CancellationToken ct)
    {
        var delaySeconds = _options.InitialReconnectDelaySeconds;

        while (!ct.IsCancellationRequested)
        {
            try
            {
                await ConnectOnceAsync(ct).ConfigureAwait(false);
                // ConnectOnceAsync returns only after the session disconnects.
                delaySeconds = _options.InitialReconnectDelaySeconds; // reset after success
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Connection attempt failed; retrying in {Delay}s", delaySeconds);
            }

            await DelayAsync(delaySeconds, ct).ConfigureAwait(false);
            delaySeconds = Math.Min(delaySeconds * 2, _options.MaxReconnectDelaySeconds);
        }

        _logger.LogInformation("TuyaMcpClient stopped");
    }

    // ─── Single connection attempt ────────────────────────────────────────────

    private async Task ConnectOnceAsync(CancellationToken ct)
    {
        if (_session is not null)
        {
            await _session.DisposeAsync().ConfigureAwait(false);
            _session = null;
        }

        // Step 1: authenticate
        await _auth!.RegisterAsync(ct).ConfigureAwait(false);

        // Step 2: build session + handler
        _session = new TuyaMcpSession(_options, _auth, _logger);
        var handler = new TuyaMcpHandler(_options, _session, _logger);

        // Wire handler events → reconnect triggers
        var tcs = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        _session.Disconnected += () =>
        {
            tcs.TrySetResult();
            return Task.CompletedTask;
        };

        handler.KickoutRequested += () =>
        {
            _logger.LogWarning("Kickout received; will re-register and reconnect");
            tcs.TrySetResult();
            return Task.CompletedTask;
        };

        handler.MigrateRequested += () =>
        {
            _logger.LogInformation("Migrate received; reconnecting");
            tcs.TrySetResult();
            return Task.CompletedTask;
        };

        // Wire session.MessageReceived → handler
        _session.MessageReceived += frame =>
            handler.HandleFrameAsync(frame, _auth.Token);

        // Step 3: connect WebSocket
        await _session.ConnectAsync(ct).ConfigureAwait(false);

        // Wait until disconnected (or cancellation)
        using var reg = ct.Register(() => tcs.TrySetCanceled());
        await tcs.Task.ConfigureAwait(false);
    }

    // ─── Helpers ─────────────────────────────────────────────────────────────

    private static async Task DelayAsync(int seconds, CancellationToken ct)
    {
        try { await Task.Delay(TimeSpan.FromSeconds(seconds), ct).ConfigureAwait(false); }
        catch (OperationCanceledException) { /* expected */ }
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync().ConfigureAwait(false);
        _httpClient.Dispose();
        _runCts?.Dispose();
    }
}
