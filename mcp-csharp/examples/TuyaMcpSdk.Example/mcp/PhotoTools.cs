using System.ComponentModel;
using ModelContextProtocol.Server;

namespace TuyaMcpSdk.Example.mcp;

/// <summary>
/// Photo tools for the mock MCP server.
/// Mirrors examples/mcp/pic/ tools from the Python SDK.
/// </summary>
[McpServerToolType]
public sealed class PhotoTools
{
    private static readonly List<string> _photos = [];

    [McpServerTool, Description("Take a photo and save it with the given name. Returns the saved photo name.")]
    public static string TakePhoto(
        [Description("Name for the photo, e.g. 'photo1'")] string name)
    {
        var photoName = $"{name}_{DateTime.UtcNow:yyyyMMddHHmmss}.jpg";
        _photos.Add(photoName);
        return $"Photo saved: {photoName}";
    }

    [McpServerTool, Description("View photos matching a keyword. Returns a list of matching photo names.")]
    public static string ViewPhoto(
        [Description("Keyword to filter photos, e.g. 'photo1'")] string keyword)
    {
        var matches = _photos
            .Where(p => p.Contains(keyword, StringComparison.OrdinalIgnoreCase))
            .ToList();

        return matches.Count == 0
            ? $"No photos found matching '{keyword}'."
            : $"Found {matches.Count} photo(s): {string.Join(", ", matches)}";
    }
}
