using System.ComponentModel;
using ModelContextProtocol.Server;

namespace TuyaMcpSdk.Example.mcp;

/// <summary>
/// Music tools for the mock MCP server.
/// Mirrors examples/mcp/music/ tools from the Python SDK.
/// </summary>
[McpServerToolType]
public sealed class MusicTools
{
    private static string? _currentSong;

    [McpServerTool, Description("Play music by keyword. Returns the name of the song being played.")]
    public static string PlayMusic(
        [Description("Keyword to search for a song, e.g. 'classic', 'jazz', 'rock'")] string keyword)
    {
        _currentSong = $"Song matching '{keyword}'";
        return $"Now playing: {_currentSong}";
    }

    [McpServerTool, Description("Stop the currently playing music.")]
    public static string StopMusic()
    {
        if (_currentSong is null)
            return "No music is currently playing.";

        var stopped = _currentSong;
        _currentSong = null;
        return $"Stopped: {stopped}";
    }
}
