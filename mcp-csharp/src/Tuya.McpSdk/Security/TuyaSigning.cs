using System.Security.Cryptography;
using System.Text;

namespace Tuya.McpSdk.Security;

/// <summary>
/// Signing helpers that mirror utils/sign.go in the Go SDK.
///
/// Two signing modes:
///   1. RestfulSign  – used for HTTP header auth on the registration API.
///   2. WsDataSign   – used to sign / verify individual WebSocket message frames.
/// </summary>
internal static class TuyaSigning
{
    // ─── Primitive ──────────────────────────────────────────────────────────

    /// <summary>HMAC-SHA256 over <paramref name="input"/>, keyed by <paramref name="secret"/>; returns uppercase hex.</summary>
    public static string HmacSha256Hex(string secret, string input)
    {
        var keyBytes  = Encoding.UTF8.GetBytes(secret);
        var dataBytes = Encoding.UTF8.GetBytes(input);
        var hash      = HMACSHA256.HashData(keyBytes, dataBytes);
        return Convert.ToHexString(hash); // uppercase, no dashes
    }

    /// <summary>Constant-time comparison to defend against timing attacks.</summary>
    public static bool HmacSha256Verify(string secret, string input, string expectedHex)
    {
        var computed = HmacSha256Hex(secret, input);
        return CryptographicOperations.FixedTimeEquals(
            Encoding.ASCII.GetBytes(computed),
            Encoding.ASCII.GetBytes(expectedHex));
    }

    /// <summary>32-character lowercase hex nonce (16 random bytes).</summary>
    public static string NewNonce()
    {
        Span<byte> buf = stackalloc byte[16];
        RandomNumberGenerator.Fill(buf);
        return Convert.ToHexString(buf).ToLowerInvariant();
    }

    /// <summary>Current UTC time as Unix epoch milliseconds string.</summary>
    public static string UnixTimeMs() =>
        DateTimeOffset.UtcNow.ToUnixTimeMilliseconds().ToString();

    // ─── REST header signing (mirrors RestfulSigner.genSignStr in Go) ────────

    /// <summary>
    /// Builds the canonical signing string for HTTP REST requests and returns
    /// the HMAC-SHA256 signature.
    ///
    /// Canonical form (mirrors Go RestfulSigner):
    ///   {access_id}\n{t}\n{sign_method}\n{nonce}\n
    ///   \n{sorted_query_params_or_empty}\n{payload_or_empty}\n{path}
    /// </summary>
    public static string SignRestRequest(
        string secret,
        string accessId,
        string timestamp,
        string nonce,
        string path,
        string? queryParams = null,
        string? payload     = null)
    {
        var headerPart = $"{accessId}\n{timestamp}\nHMAC-SHA256\n{nonce}\n";
        var queryPart  = queryParams ?? string.Empty;
        var bodyPart   = payload     ?? string.Empty;
        var signStr    = $"{headerPart}\n{queryPart}\n{bodyPart}\n{path}";
        return HmacSha256Hex(secret, signStr);
    }

    // ─── WebSocket frame signing (mirrors WsDataSigner.genSignStr in Go) ────

    /// <summary>
    /// Builds the canonical signing string for a WebSocket message frame.
    ///
    /// Canonical form: sorted key-value pairs (excluding "sign") joined as
    ///   key:value\n  (without trailing newline on last entry)
    /// </summary>
    private static string WsSignStr(IReadOnlyDictionary<string, string> fields)
    {
        var pairs = fields
            .Where(kv => kv.Key != "sign")
            .OrderBy(kv => kv.Key, StringComparer.Ordinal)
            .Select(kv => $"{kv.Key}:{kv.Value}");
        return string.Join('\n', pairs);
    }

    /// <summary>Signs a WebSocket message frame; returns uppercase hex signature.</summary>
    public static string SignWsFrame(IReadOnlyDictionary<string, string> fields, string token) =>
        HmacSha256Hex(token, WsSignStr(fields));

    /// <summary>Verifies a WebSocket message frame signature.</summary>
    public static bool VerifyWsFrame(IReadOnlyDictionary<string, string> fields, string token, string sign) =>
        HmacSha256Verify(token, WsSignStr(fields), sign);
}
