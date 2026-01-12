"""
MCP SDK Quick Start - Async Optimized Version
Simplified version based on native asyncio, no subprocess and file state synchronization required
"""

import asyncio
import logging
import os
import sys
import signal
import time
from pathlib import Path

# Add src path to import mcp_sdk
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Try to import mcp_sdk with fallback
try:
    from mcp_sdk import create_mcpsdk
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False
    raise ImportError("mcp_sdk package is required but not available")

# Configure logging
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mcpsdk_async.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)


class AsyncMCPSDKClient:
    """MCP SDK client based on asyncio"""

    def __init__(self, config: dict):
        self.config = config
        self.mcpsdk = None
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def startup(self):
        """Start SDK"""
        try:
            if not MCP_SDK_AVAILABLE:
                raise ImportError(
                    "mcp_sdk package is required but not available")

            logger.info("Starting MCP SDK (Async version)...")

            # Create SDK instance
            self.mcpsdk = create_mcpsdk(
                endpoint=self.config['endpoint'],
                access_id=self.config['access_id'],
                access_secret=self.config['access_secret'],
                custom_mcp_server_endpoint=self.config.get(
                    'custom_mcp_server_endpoint')
            )

            # Start SDK (using context manager)
            await self.mcpsdk.startup()

            # Start background listening
            await self.mcpsdk.start_background()

            self._running = True
            logger.info("MCP SDK started successfully!")
            logger.info("   Connected: %s", self.mcpsdk.is_connected)
            logger.info("   Running: %s", self.mcpsdk.is_running)
            logger.info(
                "   Custom MCP Server: %s", self.config.get('custom_mcp_server_endpoint'))

        except Exception as e:
            logger.error("Failed to start MCP SDK: %s", e)
            raise

    async def run(self):
        """Run SDK and monitor status"""
        if not self.mcpsdk:
            await self.startup()

        # Set up signal handling
        self._setup_signal_handlers()

        try:
            logger.info("MCP SDK is running, starting health monitoring...")

            # Health monitoring loop
            check_count = 0
            while self._running and not self._shutdown_event.is_set():
                check_count += 1

                # Check connection status
                is_connected = self.mcpsdk.is_connected
                is_running = self.mcpsdk.is_running

                if is_connected and is_running:
                    if check_count % 6 == 0:  # Print once per minute
                        logger.info(
                            "MCP SDK healthy - Check #%s", check_count)
                elif is_running and not is_connected:
                    logger.warning(
                        "MCP SDK reconnecting... - Check #%s", check_count)
                else:
                    logger.error(
                        "MCP SDK not running - Check #%s", check_count)
                    break

                await asyncio.sleep(10)

        except asyncio.CancelledError:
            logger.info("MCP SDK monitoring cancelled")
        except KeyboardInterrupt:
            logger.info("MCP SDK stopped by user")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down MCP SDK...")
        self._running = False
        self._shutdown_event.set()

        if self.mcpsdk:
            try:
                await self.mcpsdk.shutdown()
                logger.info("MCP SDK shutdown completed")
            except Exception as e:
                logger.error("Error during shutdown: %s", e)

    def _setup_signal_handlers(self):
        """Set up signal handling"""
        def signal_handler():
            logger.info("Received shutdown signal...")
            asyncio.create_task(self.shutdown())

        # Set up signal handlers
        for sig in [signal.SIGTERM, signal.SIGINT]:
            try:
                asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                # Windows does not support add_signal_handler
                signal.signal(sig, lambda s, f: signal_handler())

    @property
    def is_healthy(self) -> bool:
        """Check if healthy"""
        return bool(self._running and self.mcpsdk and self.mcpsdk.is_connected and self.mcpsdk.is_running)


async def create_client_from_config(config: dict) -> AsyncMCPSDKClient:
    """Create client instance from configuration (factory function)"""
    client = AsyncMCPSDKClient(config)
    await client.startup()
    return client


async def quick_start_async():
    """Async version quick start"""

    # Get configuration from environment variables
    config = {
        'endpoint': os.getenv('ENDPOINT', 'your-endpoint'),
        'access_id': os.getenv('ACCESS_ID', 'your-access-id'),
        'access_secret': os.getenv('ACCESS_SECRET', 'your-access-secret'),
        'custom_mcp_server_endpoint': os.getenv('CUSTOM_MCP_SERVER_ENDPOINT', 'http://localhost:8765/mcp')
    }

    logger.info("MCP SDK Quick Start - Async Version")
    logger.info("=" * 50)
    logger.info("Configuration:")
    logger.info("  Endpoint: %s", config['endpoint'])
    logger.info("  Access ID: %s", config['access_id'])
    logger.info(
        "  Custom MCP Server: %s", config['custom_mcp_server_endpoint'])
    logger.info("=" * 50)

    client = AsyncMCPSDKClient(config)

    try:
        # Start and run client
        await client.run()

    except KeyboardInterrupt:
        logger.info("Quick start stopped by user")
    except Exception as e:
        logger.error("Error in quick start: %s", e)
        raise
    finally:
        await client.shutdown()


async def run_with_performance_monitoring():
    """Run with performance monitoring"""

    start_time = time.time()

    try:
        import psutil
        psutil_available = True
        process = psutil.Process()

        # Record initial resource usage
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        initial_cpu = process.cpu_percent()
        logger.info(
            "Starting performance monitoring - Initial memory: %sMB, CPU: %s%%", initial_memory, initial_cpu)
    except ImportError:
        psutil_available = False
        logger.warning("psutil not available, performance monitoring disabled")

    try:
        await quick_start_async()
    finally:
        # Record final resource usage
        end_time = time.time()

        if psutil_available:
            final_memory = process.memory_info().rss / 1024 / 1024  # MB

            logger.info("=" * 50)
            logger.info("Performance Statistics:")
            logger.info("  Runtime: %s", end_time - start_time)
            logger.info(
                "  Memory usage: %sMB → %sMB", initial_memory, final_memory)
            logger.info(
                "  Memory efficiency: %s", 'Improved' if final_memory < initial_memory * 1.1 else 'Normal')
            logger.info("=" * 50)
        else:
            logger.info("=" * 50)
            logger.info("Performance Statistics:")
            logger.info("  Runtime: %s", end_time - start_time)
            logger.info(
                "  Performance monitoring not available (psutil not installed)")
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
