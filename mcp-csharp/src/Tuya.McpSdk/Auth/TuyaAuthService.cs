using System.Net.Http.Json;
using Microsoft.Extensions.Logging;
using Tuya.McpSdk.Protocol;
using Tuya.McpSdk.Security;

namespace Tuya.McpSdk.Auth;

/// <summary>
/// Handles Tuya platform registration and WebSocket connection header generation.
/// Mirrors auth.go (AuthToken) in the Go SDK.
/// </summary>
internal sealed class TuyaAuthService
{
    private readonly TuyaMcpOptions _options;
    private readonly HttpClient     _http;
    private readonly ILogger        _logger;

    private string _token    = string.Empty;
    private string _clientId = string.Empty;

    public TuyaAuthService(TuyaMcpOptions options, HttpClient http, ILogger logger)
    {
        _options = options;
        _http    = http;
        _logger  = logger;
    }

    /// <summary>Current auth token (valid after <see cref="RegisterAsync"/>).</summary>
    public string Token    => _token;

    /// <summary>Client ID assigned by the Tuya gateway (valid after <see cref="RegisterAsync"/>).</summary>
    public string ClientId => _clientId;

    // ─── Registration ────────────────────────────────────────────────────────

    /// <summary>
    /// Calls GET /v1/client/registration with HMAC-SHA256 signed headers to obtain
    /// an auth token and client_id.  Mirrors AuthToken.Auth() in Go.
    /// </summary>
    public async Task RegisterAsync(CancellationToken ct = default)
    {
        var ts    = TuyaSigning.UnixTimeMs();
        var nonce = TuyaSigning.NewNonce();
        var path  = "/v1/client/registration";

        var sign = TuyaSigning.SignRestRequest(
            _options.AccessSecret,
            _options.AccessId,
            ts,
            nonce,
            path);

        var registrationUrl = BuildRestUrl(path);
        _logger.LogInformation("Requesting auth token from {Url}", registrationUrl);

        using var request = new HttpRequestMessage(HttpMethod.Get, registrationUrl);
        request.Headers.TryAddWithoutValidation("access_id",   _options.AccessId);
        request.Headers.TryAddWithoutValidation("t",           ts);
        request.Headers.TryAddWithoutValidation("nonce",       nonce);
        request.Headers.TryAddWithoutValidation("sign_method", "HMAC-SHA256");
        request.Headers.TryAddWithoutValidation("sign",        sign);

        using var response = await _http.SendAsync(request, ct).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();

        var body = await response.Content.ReadFromJsonAsync<TuyaAuthApiResponse>(cancellationToken: ct)
                   ?? throw new InvalidOperationException("Empty response body from Tuya auth API.");

        if (!body.Success || body.Data is null)
            throw new InvalidOperationException($"Tuya auth failed. success={body.Success}, data={body.Data}");

        _token    = body.Data.Token;
        _clientId = body.Data.ClientId;

        _logger.LogInformation("Registered successfully. client_id={ClientId}", _clientId);
    }

    // ─── WebSocket connection header ─────────────────────────────────────────

    /// <summary>
    /// Builds the WebSocket URL and HMAC-signed headers needed to connect to /ws/mcp.
    /// Mirrors AuthToken.ConnectHeader() in Go.
    /// </summary>
    public (Uri WsUri, Dictionary<string, string> Headers) BuildWsConnectParams()
    {
        var ts    = TuyaSigning.UnixTimeMs();
        var nonce = TuyaSigning.NewNonce();
        var path  = "/ws/mcp";

        // The WS URL has ?client_id=… appended as a query parameter.
        var wsBase  = BuildWsUrl(path);
        var fullUrl = $"{wsBase}?client_id={Uri.EscapeDataString(_clientId)}";

        // Query string used in signing (sorted; key=value&… without trailing &)
        var queryPart = $"client_id={_clientId}";

        // Signing uses the auth token (not the access secret) for WS connect.
        var sign = TuyaSigning.SignRestRequest(
            _token,
            _options.AccessId,
            ts,
            nonce,
            path,
            queryPart);

        _logger.LogInformation("Connecting WebSocket to {Url}", fullUrl);

        var headers = new Dictionary<string, string>
        {
            ["access_id"]   = _options.AccessId,
            ["t"]           = ts,
            ["nonce"]       = nonce,
            ["sign_method"] = "HMAC-SHA256",
            ["sign"]        = sign
        };

        return (new Uri(fullUrl), headers);
    }

    // ─── Helpers ─────────────────────────────────────────────────────────────

    private string BuildRestUrl(string path)
    {
        var builder = new UriBuilder(_options.Endpoint) { Path = path };
        return builder.Uri.ToString();
    }

    private string BuildWsUrl(string path)
    {
        var builder = new UriBuilder(_options.Endpoint) { Path = path };
        builder.Scheme = builder.Scheme switch
        {
            "http"  => "ws",
            "https" => "wss",
            _       => builder.Scheme
        };
        return builder.Uri.ToString();
    }
}
