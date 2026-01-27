"""
MCP SDK Quick Start - Async Optimized Version
Simplified version based on native asyncio, no subprocess and file state synchronization required
"""

import asyncio
import importlib
import json
import logging
import os
import signal
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add src path to import mcp_sdk
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from mcp_sdk import create_mcpsdk
except ImportError:
    raise ImportError("mcp_sdk package is required but not available")

HeaderDict = dict[str, str]
HeaderProvider = Callable[[], HeaderDict | Awaitable[HeaderDict] | None]


def _parse_headers_json(value: str) -> HeaderDict:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("headers JSON must be an object")

    out: HeaderDict = {}
    for k, v in parsed.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError("headers JSON must have string keys and string values")
        out[k] = v
    return out


def _configure_windows_utf8() -> None:
    if sys.platform != "win32":
        return

    stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(stdout_reconfigure):
        _ = stdout_reconfigure(encoding="utf-8")

    stderr_reconfigure = getattr(sys.stderr, "reconfigure", None)
    if callable(stderr_reconfigure):
        _ = stderr_reconfigure(encoding="utf-8")


_configure_windows_utf8()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("mcpsdk_async.log", mode="w"),
    ],
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QuickStartConfig:
    endpoint: str
    access_id: str
    access_secret: str
    custom_mcp_server_endpoint: str | None = None
    static_mcp_headers: HeaderDict | None = None

    @staticmethod
    def from_env() -> "QuickStartConfig":
        static_headers_json = os.getenv("STATIC_MCP_HEADERS_JSON")
        static_headers: HeaderDict | None = None
        if static_headers_json:
            static_headers = _parse_headers_json(static_headers_json)

        return QuickStartConfig(
            endpoint=os.getenv("ENDPOINT", "your-endpoint"),
            access_id=os.getenv("ACCESS_ID", "your-access-id"),
            access_secret=os.getenv("ACCESS_SECRET", "your-access-secret"),
            custom_mcp_server_endpoint=os.getenv(
                "CUSTOM_MCP_SERVER_ENDPOINT", "http://localhost:8765/mcp"
            ),
            static_mcp_headers=static_headers,
        )


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    def signal_handler() -> None:
        logger.info("Received shutdown signal...")
        stop_event.set()

    for sig in [signal.SIGTERM, signal.SIGINT]:
        try:
            asyncio.get_running_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            signal.signal(sig, lambda _s, _f: signal_handler())


async def quick_start_async(config: QuickStartConfig) -> None:
    logger.info("MCP SDK Quick Start - Async Version")
    logger.info("=" * 50)
    logger.info("Configuration:")
    logger.info("  Endpoint: %s", config.endpoint)
    logger.info("  Access ID: %s", config.access_id)
    logger.info("  Custom MCP Server: %s", config.custom_mcp_server_endpoint)
    logger.info("  Static MCP headers: %s", config.static_mcp_headers)
    logger.info("=" * 50)

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    async with create_mcpsdk(
        endpoint=config.endpoint,
        access_id=config.access_id,
        access_secret=config.access_secret,
        custom_mcp_server_endpoint=config.custom_mcp_server_endpoint,
        headers=config.static_mcp_headers
    ) as sdk:
        await sdk.start_background()

        check_count = 0
        while not stop_event.is_set() and sdk.is_running:
            check_count += 1

            if sdk.is_connected and sdk.is_running:
                if check_count % 6 == 0:  # Print once per minute
                    logger.info("MCP SDK healthy - Check #%s", check_count)
            elif sdk.is_running and not sdk.is_connected:
                logger.warning("MCP SDK reconnecting... - Check #%s", check_count)
            else:
                logger.error("MCP SDK not running - Check #%s", check_count)
                break

            await asyncio.sleep(10)


async def run_with_performance_monitoring():
    """Run with performance monitoring"""

    start_time = time.time()

    psutil_available = False
    process: Any | None = None
    initial_memory: float | None = None

    try:
        psutil = importlib.import_module("psutil")
        psutil_available = True
        proc: Any = psutil.Process()
        process = proc
        initial_memory = float(proc.memory_info().rss) / 1024 / 1024  # MB
        initial_cpu = proc.cpu_percent()
        logger.info(
            "Starting performance monitoring - Initial memory: %sMB, CPU: %s%%",
            initial_memory,
            initial_cpu,
        )
    except ModuleNotFoundError:
        logger.warning("psutil not available, performance monitoring disabled")

    try:
        await quick_start_async(QuickStartConfig.from_env())
    finally:
        # Record final resource usage
        end_time = time.time()

        if psutil_available and process is not None and initial_memory is not None:
            final_memory = float(process.memory_info().rss) / 1024 / 1024  # MB

            logger.info("=" * 50)
            logger.info("Performance Statistics:")
            logger.info("  Runtime: %s", end_time - start_time)
            logger.info("  Memory usage: %sMB → %sMB", initial_memory, final_memory)
            logger.info(
                "  Memory efficiency: %s",
                "Improved" if final_memory < initial_memory * 1.1 else "Normal",
            )
            logger.info("=" * 50)
        else:
            logger.info("=" * 50)
            logger.info("Performance Statistics:")
            logger.info("  Runtime: %s", end_time - start_time)
            logger.info("  Performance monitoring not available (psutil not installed)")
            logger.info("=" * 50)


if __name__ == "__main__":
    try:
        # Use uvloop for performance improvement (if available)
        try:
            import uvloop

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("Using uvloop for performance improvement")
        except ImportError:
            logger.info("Using default asyncio event loop")

        # Run version with performance monitoring
        asyncio.run(run_with_performance_monitoring())

    except KeyboardInterrupt:
        logger.error("Service stopped")
    except Exception as e:
        logger.error("Startup failed: %s", e, exc_info=True)
        sys.exit(1)
