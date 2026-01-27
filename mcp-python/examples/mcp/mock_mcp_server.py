"""
Mock MCP Server using FastMCP
Mock MCP server using FastMCP framework for testing SDK's MCP client functionality
"""

import asyncio
import glob
import logging
import os
import platform
import subprocess
from datetime import datetime
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field
from starlette.requests import Request
from starlette.responses import PlainTextResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockMCPServer:
    """Mock MCP server using FastMCP with photo and music tools"""

    def __init__(self):
        # Create FastMCP application instance

        self.app = FastMCP("Mock MCP Server")

        # Register tools
        self._register_tools()

        logger.info("Mock MCP Server initialized with FastMCP")

    def _register_tools(self):
        """Register tools: take_photo and play_music"""

        @self.app.tool
        def take_photo(
            name: Annotated[
                str, Field(description="The name of the photo; e.g. 'photo1'")
            ],
            is_view: Annotated[
                bool,
                Field(
                    default=False,
                    description="Whether to view the photo after taking it; e.g. 'true'",
                ),
            ] = False,
        ) -> str:
            """
            Take a photo
            """
            try:
                # Get the current directory and create pic directory path
                current_dir = os.path.dirname(os.path.abspath(__file__))
                photo_dir = os.path.join(current_dir, "pic")

                # Create pic directory if it doesn't exist
                if not os.path.exists(photo_dir):
                    os.makedirs(photo_dir, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"{name}_{timestamp}.jpg"
                file_path = os.path.join(photo_dir, filename)

                system = platform.system()

                if system == "Darwin":  # macOS
                    try:
                        # Use imagesnap if available (needs to be installed: brew install imagesnap)
                        result = subprocess.run(
                            ["imagesnap", file_path],
                            capture_output=True,
                            text=True,
                            check=True,
                        )
                        if result.returncode == 0:
                            response = f"Photo taken successfully: {name}"
                            if is_view:
                                subprocess.Popen(["open", file_path])
                                response = (
                                    f"Photo taken successfully and viewed: {name}"
                                )
                            return response
                        else:
                            return "Error: imagesnap not found or failed. Install with: brew install imagesnap"
                    except FileNotFoundError:
                        return "Error: imagesnap not found. Install with: brew install imagesnap"

                elif system == "Windows":  # Windows
                    # For Windows, we'll use a placeholder approach
                    return "Photo capture on Windows requires additional software. Consider using built-in Camera app."

                elif system == "Linux":  # Linux
                    # Try fswebcam or other tools
                    tools = [
                        (
                            ["fswebcam", "-r", "640x480", "--no-banner", file_path],
                            "fswebcam",
                        ),
                        (
                            [
                                "ffmpeg",
                                "-f",
                                "v4l2",
                                "-i",
                                "/dev/video0",
                                "-vframes",
                                "1",
                                file_path,
                            ],
                            "ffmpeg",
                        ),
                    ]

                    for cmd, tool_name in tools:
                        try:
                            result = subprocess.run(
                                cmd, capture_output=True, text=True, check=True
                            )
                            if result.returncode == 0:
                                response = f"Photo taken successfully: {name}"
                                if is_view:
                                    subprocess.Popen(["xdg-open", file_path])
                                    response = (
                                        f"Photo taken successfully and viewed: {name}"
                                    )
                                return response
                        except FileNotFoundError:
                            continue
                    return "Error: No suitable camera tool found on Linux. Try installing fswebcam or ffmpeg."

                else:
                    return "Error: Unsupported operating system: {system}"

            except Exception as e:
                logger.error("Take photo error: %s", e)
                return f"Failed to take photo: {str(e)}"

        @self.app.tool
        def view_photo(
            name: Annotated[
                str, Field(description="The name of the photo; e.g. 'photo1'")
            ],
        ) -> str:
            """
            View a photo
            """
            try:
                # Get the current directory and photo directory path
                current_dir = os.path.dirname(os.path.abspath(__file__))
                photo_dir = os.path.join(current_dir, "pic")

                if not os.path.exists(photo_dir):
                    return f"Photo directory not found: {photo_dir}"

                # Find photo files that start with the given name
                photo_files = glob.glob(os.path.join(photo_dir, f"{name}*"))

                if not photo_files:
                    return f"No photos found with name: {name}"

                # Use the first matching photo
                photo_path = photo_files[0]
                system = platform.system()

                if system == "Darwin":  # macOS
                    subprocess.Popen(["open", photo_path])
                elif system == "Windows":  # Windows
                    subprocess.Popen(["start", "", photo_path], shell=True)
                elif system == "Linux":  # Linux
                    subprocess.Popen(["xdg-open", photo_path])
                else:
                    return f"Error: Unsupported operating system: {system}"

                return "Photo viewed successfully"

            except Exception as e:
                logger.error("View photo error: %s", e)
                return f"Failed to view photo: {str(e)}"

        @self.app.tool
        def play_music(
            name: Annotated[str, Field(description="Music name; e.g. 'classic'")],
        ) -> str:
            """
            Play music by music name
            """
            try:
                # Get the current directory and music directory path
                current_dir = os.path.dirname(os.path.abspath(__file__))
                music_dir = os.path.join(current_dir, "music")

                # If music directory doesn't exist in current location, try examples/ prefix
                if not os.path.exists(music_dir):
                    music_dir = os.path.join("examples", current_dir, "music")

                if not os.path.exists(music_dir):
                    return f"Music directory not found: {music_dir}"

                # Find music files that contain the music_name
                music_files = []
                for file in os.listdir(music_dir):
                    if file.lower().find(name.lower()) != -1 and file.lower().endswith(
                        (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
                    ):
                        music_files.append(file)

                if not music_files:
                    available_files = [
                        f
                        for f in os.listdir(music_dir)
                        if f.lower().endswith(
                            (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
                        )
                    ]
                    return f"Music not found: {name}\nAvailable music files: {', '.join(available_files) if available_files else 'None'}"

                # Use the first matching music file
                music_file = music_files[0]
                music_path = os.path.join(music_dir, music_file)
                system = platform.system()

                if system == "Darwin":  # macOS
                    subprocess.Popen(["open", music_path])
                elif system == "Windows":  # Windows
                    subprocess.Popen(["start", "", music_path], shell=True)
                elif system == "Linux":  # Linux
                    # Try common Linux media players
                    players = ["xdg-open", "vlc", "mplayer", "mpv"]
                    for player in players:
                        try:
                            subprocess.Popen([player, music_path])
                            break
                        except FileNotFoundError:
                            continue
                else:
                    return f"Error: Unsupported operating system: {system}"

                return f"Playing music: {name}"

            except Exception as e:
                logger.error("Play music error: %s", e)
                return f"Failed to play music: {str(e)}"

        @self.app.tool
        def stop_music() -> str:
            """
            Stop playing music
            """
            try:
                system = platform.system()

                if system == "Darwin":  # macOS
                    # Kill music/media applications
                    subprocess.run(
                        ["pkill", "-f", "Music"], capture_output=True, check=True
                    )
                    subprocess.run(
                        ["pkill", "-f", "VLC"], capture_output=True, check=True
                    )
                elif system == "Windows":  # Windows
                    # Kill common media players
                    subprocess.run(
                        ["taskkill", "/f", "/im", "wmplayer.exe"],
                        capture_output=True,
                        check=True,
                    )
                    subprocess.run(
                        ["taskkill", "/f", "/im", "vlc.exe"],
                        capture_output=True,
                        check=True,
                    )
                elif system == "Linux":  # Linux
                    # Kill common media players
                    subprocess.run(
                        ["pkill", "-f", "vlc"], capture_output=True, check=True
                    )
                    subprocess.run(
                        ["pkill", "-f", "mplayer"], capture_output=True, check=True
                    )
                    subprocess.run(
                        ["pkill", "-f", "mpv"], capture_output=True, check=True
                    )
                else:
                    return f"Error: Unsupported operating system: {system}"

                return "Music stopped"

            except Exception as e:
                logger.error("Stop music error: %s", e)
                return f"Failed to stop music: {str(e)}"

        logger.info("Tools registered: take_photo, view_photo, play_music, stop_music")

    async def start_stdio(self):
        """Start MCP server in stdio mode"""
        logger.info("Mock MCP Server with FastMCP")
        logger.info("=" * 50)
        logger.info("This server simulates an MCP server using FastMCP framework.")
        logger.info("")
        logger.info("Available capabilities:")
        logger.info("- Tools: take_photo, view_photo, play_music, stop_music")
        logger.info("")
        logger.info("Communication: stdio (JSON-RPC 2.0)")
        logger.info("=" * 50)

        # Use FastMCP stdio mode
        await self.app.run_stdio_async()

    async def start_server(self, host: str = "localhost", port: int = 8765):
        """Start HTTP server mode"""

        @self.app.custom_route("/health", methods=["GET"])
        async def health_check(_: Request) -> PlainTextResponse:
            return PlainTextResponse("OK")

        logger.info("Starting Mock MCP Server on http://%s:%s", host, port)
        await self.app.run_http_async(host=host, port=port)

    def get_app(self):
        """Get FastMCP application instance"""
        return self.app


async def main():
    """Start mock MCP server"""
    server = MockMCPServer()

    # Default to HTTP server mode
    await server.start_server(host="localhost", port=8765)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Mock MCP Server stopped.")
    except Exception as e:
        logger.error("Error starting server: %s", e)
        raise
