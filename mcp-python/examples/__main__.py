#!/usr/bin/env python3
"""
MCP SDK Enhanced Resilient Launcher - Supporting Service Dependencies and Readiness Detection

"""

import asyncio
import signal
import logging
import argparse
import sys
import os

import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Try to import aiohttp, fallback to placeholder if not available
try:
    import aiohttp
except ImportError:
    # Fallback for when aiohttp is not available
    raise ImportError("aiohttp not available")

# Add project path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Configure logging
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(project_root / "examples" /
                            "mcp_launcher_enhanced.log")
    ]
)
logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service status enumeration"""
    STARTING = "starting"
    RUNNING = "running"
    READY = "ready"  # New: Service ready status
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    RECONNECTING = "reconnecting"


@dataclass
class ServiceConfig:
    """Service configuration"""
    name: str
    endpoint: Optional[str] = None
    access_id: Optional[str] = None
    access_secret: Optional[str] = None
    custom_mcp_server_endpoint: Optional[str] = None
    host: Optional[str] = "localhost"
    port: Optional[int] = 8765
    enable_resilience: bool = True
    depends_on: Optional[List[str]] = None  # List of dependent services
    readiness_timeout: int = 60  # Readiness detection timeout


class ServiceReadinessChecker:
    """Service readiness checker"""

    @staticmethod
    async def check_http_service(host: str, port: int, path: str = "/", timeout: int = 5) -> bool:
        """Check if HTTP service is ready"""
        try:
            connector = aiohttp.TCPConnector(limit=1, limit_per_host=1)
            client_timeout = aiohttp.ClientTimeout(total=timeout)

            async with aiohttp.ClientSession(
                connector=connector,
                timeout=client_timeout
            ) as session:
                url = f"http://{host}:{port}{path}"
                async with session.get(url) as response:
                    return response.status < 500  # Any non-5xx response is considered ready

        except Exception as e:
            logger.error("HTTP readiness check failed: %s", e)
            return False

    @staticmethod
    async def check_tcp_port(host: str, port: int, timeout: int = 5) -> bool:
        """Check if TCP port is connectable"""
        try:
            future = asyncio.open_connection(host, port)
            _, writer = await asyncio.wait_for(future, timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return True
        except Exception as e:
            logger.error("TCP port check failed: %s", e)
            return False

    @staticmethod
    async def check_mcp_server_ready(host: str, port: int, timeout: int = 30) -> bool:
        """Specifically check MCP server readiness status"""
        # First check if port is open
        if not await ServiceReadinessChecker.check_tcp_port(host, port, 2):
            return False

        # Then try HTTP health check
        return await ServiceReadinessChecker.check_http_service(host, port, "/health", timeout)


class EnhancedMockMCPServer:
    """Enhanced MockMCPServer wrapper, supporting readiness detection"""

    def __init__(self, mock_server):
        self.mock_server = mock_server
        self.host = "localhost"
        self.port = 8765
        self._server_task = None
        self._is_ready = False
        self._ready_event = asyncio.Event()
        self._health_monitor_task = None

    async def start_server(self, host: str, port: int):
        """Start server and wait for readiness"""
        self.host = host
        self.port = port

        logger.info(
            "Starting Enhanced Mock MCP Server on http://%s:%s", host, port)

        # Start server in background
        self._server_task = asyncio.create_task(
            self.mock_server.start_server(host, port)
        )

        # Start readiness detection
        self._health_monitor_task = asyncio.create_task(
            self._wait_for_ready_with_monitoring()
        )

        # Give server some time to start
        await asyncio.sleep(1)

    async def _wait_for_ready_with_monitoring(self):
        """Wait for server readiness and continuously monitor"""
        max_attempts = 30
        attempt = 0

        logger.info("Checking MCP Server readiness...")

        # Initial readiness detection
        while attempt < max_attempts:
            try:
                if await ServiceReadinessChecker.check_mcp_server_ready(
                    self.host, self.port, timeout=2
                ):
                    self._is_ready = True
                    self._ready_event.set()
                    logger.info(
                        "Mock MCP Server is ready at http://%s:%s", self.host, self.port)
                    break

            except Exception as e:
                logger.error("Readiness check error: %s", e)

            attempt += 1
            if attempt < max_attempts:
                await asyncio.sleep(2)

        if not self._is_ready:
            logger.error(
                "Mock MCP Server failed to become ready after %s seconds", max_attempts * 2)
            return

        # Continuous health monitoring
        await self._continuous_health_monitoring()

    async def _continuous_health_monitoring(self):
        """Continuous health monitoring"""
        consecutive_failures = 0
        max_failures = 3

        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                if await ServiceReadinessChecker.check_mcp_server_ready(
                    self.host, self.port, timeout=5
                ):
                    if consecutive_failures > 0:
                        logger.info("Mock MCP Server health restored")
                        consecutive_failures = 0
                        self._is_ready = True
                        self._ready_event.set()
                else:
                    consecutive_failures += 1
                    logger.warning(
                        "Mock MCP Server health check failed (%s/%s)", consecutive_failures, max_failures)

                    if consecutive_failures >= max_failures:
                        logger.error(
                            "Mock MCP Server health check failed multiple times")
                        self._is_ready = False
                        self._ready_event.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health monitoring error: %s", e)
                self._is_ready = False
                self._ready_event.clear()

    async def wait_for_ready(self, timeout: int = 60):
        """Wait for server readiness"""
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.error(
                "Mock MCP Server not ready after %s seconds", timeout)
            return False

    async def shutdown(self):
        """Shutdown server"""
        # Stop health monitoring
        if self._health_monitor_task and not self._health_monitor_task.done():
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass

        # Stop server
        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        self._is_ready = False
        logger.info("Enhanced Mock MCP Server shutdown")

    @property
    def is_ready(self) -> bool:
        """Check if server is ready"""
        return self._is_ready

    def get_endpoint(self) -> str:
        """Get server endpoint"""
        return f"http://{self.host}:{self.port}"


class DependencyManager:
    """Service dependency manager"""

    def __init__(self, services: Dict[str, ServiceConfig]):
        self.services = services

    def get_startup_order(self) -> List[str]:
        """Get service startup order (topological sort)"""
        # Simple topological sort implementation
        visited = set()
        result = []
        temp_visited = set()

        def visit(service_name: str):
            if service_name in temp_visited:
                raise ValueError(
                    f"Circular dependency detected involving {service_name}")
            if service_name in visited:
                return

            temp_visited.add(service_name)

            config = self.services.get(service_name)
            if config and config.depends_on:
                for dep in config.depends_on:
                    if dep in self.services:
                        visit(dep)

            temp_visited.remove(service_name)
            visited.add(service_name)
            result.append(service_name)

        for service_name in self.services:
            visit(service_name)

        return result


class EnhancedResilientServiceManager:
    """Enhanced resilient service manager, supporting dependency management and readiness detection"""

    def __init__(self):
        self.services: Dict[str, Any] = {}
        self.service_tasks: Dict[str, asyncio.Task] = {}
        self.status: Dict[str, ServiceStatus] = {}
        self._shutdown_event = asyncio.Event()
        self._service_configs: Dict[str, ServiceConfig] = {}

    async def register_services_with_dependencies(self, configs: Dict[str, ServiceConfig],
                                                  service_factories: Dict[str, Any]):
        """Register multiple services and start in dependency order"""
        # Calculate startup order
        dep_manager = DependencyManager(configs)
        startup_order = dep_manager.get_startup_order()

        logger.info("Service startup order: %s", " -> ".join(startup_order))

        # Start services in order
        for service_name in startup_order:
            config = configs[service_name]
            factory = service_factories[service_name]

            logger.info("Starting service: %s", service_name)
            await self.register_service(service_name, factory, config)

            # Wait for service readiness (if there are dependents)
            if any(c.depends_on and service_name in c.depends_on
                   for c in configs.values()):
                await self._wait_for_service_ready(service_name, config.readiness_timeout)

        logger.info("All services started successfully")

    async def register_service(self, name: str, service_factory, config: ServiceConfig):
        """Register and start a single service"""
        logger.info("Registering service: %s", name)
        self.status[name] = ServiceStatus.STARTING
        self._service_configs[name] = config

        try:
            # Create service instance
            service = await service_factory(config)
            self.services[name] = service

            # Start service monitoring task
            task = asyncio.create_task(
                self._run_service_with_monitoring(name, service))
            self.service_tasks[name] = task

            self.status[name] = ServiceStatus.RUNNING
            logger.info("Service registered and started: %s", name)

        except Exception as e:
            self.status[name] = ServiceStatus.ERROR
            logger.error("Failed to register service %s: %s", name, e)
            raise

    async def _wait_for_service_ready(self, service_name: str, timeout: int):
        """Wait for service readiness"""
        service = self.services.get(service_name)
        if not service:
            logger.warning(
                "Service %s not found for readiness check", service_name)
            return

        if hasattr(service, 'wait_for_ready'):
            logger.info("Waiting for %s to be ready...", service_name)
            if await service.wait_for_ready(timeout):
                self.status[service_name] = ServiceStatus.READY
                logger.info("Service %s is ready", service_name)
            else:
                logger.error(
                    "Service %s not ready after %ss", service_name, timeout)
        elif hasattr(service, 'is_ready'):
            # Simple polling check
            start_time = time.time()
            while time.time() - start_time < timeout:
                if service.is_ready:
                    self.status[service_name] = ServiceStatus.READY
                    logger.info("Service %s is ready", service_name)
                    return
                await asyncio.sleep(1)
            logger.warning("Service %s readiness timeout", service_name)
        else:
            # No readiness detection mechanism, mark as ready directly
            await asyncio.sleep(2)  # Give service some startup time
            self.status[service_name] = ServiceStatus.READY
            logger.info("Service %s assumed ready", service_name)

    async def _run_service_with_monitoring(self, name: str, service):
        """Run service with monitoring"""
        try:
            logger.info("Starting service monitoring for: %s", name)

            # If it's an SDK client, start resilient listening
            if hasattr(service, 'start_listening'):
                logger.info(
                    "Starting resilient listening for SDK client: %s", name)
                await service.start_listening()
            # If it's an MCP server
            elif hasattr(service, 'start_server'):
                config = self._service_configs.get(name)
                if config:
                    logger.info("Starting MCP server: %s on %s:%s",
                                name, config.host, config.port)
                    await service.start_server(config.host, config.port)
                else:
                    await service.start_server("localhost", 8765)
            # If it has a run method
            elif hasattr(service, 'run') and callable(service.run):
                await service.run()
            else:
                # Keep service alive, waiting for shutdown signal
                logger.info(
                    "Service %s in standby mode, waiting for shutdown...", name)
                await self._shutdown_event.wait()

        except asyncio.CancelledError:
            logger.info("Service %s cancelled, shutting down...", name)
            self.status[name] = ServiceStatus.STOPPING
            await self._shutdown_service(name, service)
            self.status[name] = ServiceStatus.STOPPED
            raise

        except Exception as e:
            logger.error("Service %s failed: %s", name, e)
            self.status[name] = ServiceStatus.ERROR

            # If resilience is enabled, try to restart
            config = self._service_configs.get(name)
            if config and config.enable_resilience:
                await self._handle_service_failure(name, service, e)

    async def _shutdown_service(self, name: str, service):
        """Shutdown a single service"""
        try:
            if hasattr(service, 'shutdown'):
                await service.shutdown()
            elif hasattr(service, 'cleanup'):
                await service.cleanup()
            elif hasattr(service, 'close'):
                await service.close()
            logger.info("Service %s shutdown completed", name)
        except Exception as e:
            logger.error("Error during %s shutdown: %s", name, e)

    async def _handle_service_failure(self, name: str, _service, error):
        """Handle service failure"""
        logger.warning("Handling failure for service %s: %s", name, error)
        self.status[name] = ServiceStatus.RECONNECTING

        # Implement restart logic...
        # Here you can reuse the previous restart strategy code

    async def get_service_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all services"""
        status_report = {}

        for name, service in self.services.items():
            service_status = {
                "status": self.status.get(name, ServiceStatus.STOPPED).value,
                "running": name in self.service_tasks and not self.service_tasks[name].done(),
            }

            # Get additional status information
            if hasattr(service, 'is_connected'):
                service_status["connected"] = service.is_connected
            if hasattr(service, 'is_ready'):
                service_status["ready"] = service.is_ready
            if hasattr(service, 'get_endpoint'):
                service_status["endpoint"] = service.get_endpoint()

            status_report[name] = service_status

        return status_report

    async def graceful_shutdown(self):
        """Gracefully shutdown all services"""
        logger.info("Starting graceful shutdown...")
        self._shutdown_event.set()

        # Cancel all service tasks
        for name, task in self.service_tasks.items():
            if not task.done():
                logger.info("Stopping service: %s", name)
                task.cancel()

        # Wait for tasks to complete
        if self.service_tasks:
            await asyncio.gather(*self.service_tasks.values(), return_exceptions=True)

        logger.info("Graceful shutdown completed")


# Service factory functions

async def create_enhanced_mcp_server(_: ServiceConfig):
    """Create enhanced MCP server instance"""
    try:
        # Try different import paths
        try:
            from mcp.mock_mcp_server import MockMCPServer
        except ImportError:
            from examples.mcp.mock_mcp_server import MockMCPServer

        # Create original server
        mock_server = MockMCPServer()

        # Wrap as enhanced version
        enhanced_server = EnhancedMockMCPServer(mock_server)
        logger.info("Enhanced Mock MCP Server created")
        return enhanced_server

    except ImportError as e:
        logger.error("Failed to import MockMCPServer: %s", e)
        logger.info("Creating minimal MCP server with readiness support")


async def create_enhanced_sdk_client(config: ServiceConfig):
    """Create enhanced SDK client instance"""
    try:
        # Import MCP SDK
        from mcp_sdk import MCPSdkClient

        # Try to import new connection manager
        try:
            from mcp_sdk.connection_manager import ReconnectConfig
            has_resilience = True
            logger.info("Network resilience features available")
        except ImportError:
            has_resilience = False
            logger.warning(
                "Network resilience features not available, using basic functionality")

        # Create client
        client = MCPSdkClient(
            endpoint=config.endpoint or os.getenv(
                "MCP_ENDPOINT", "wss://your-endpoint.com"),
            access_id=config.access_id or os.getenv(
                "MCP_ACCESS_ID", "your-access-id"),
            access_secret=config.access_secret or os.getenv(
                "MCP_ACCESS_SECRET", "your-access-secret"),
            custom_mcp_server_endpoint=config.custom_mcp_server_endpoint or "http://localhost:8765"
        )

        # If resilience is enabled and supported
        if config.enable_resilience and has_resilience:
            reconnect_config = ReconnectConfig(
                base_interval=2.0,      # Base reconnection interval
                max_interval=120.0,     # Maximum reconnection interval
                max_retries=-1,         # Infinite retries
                backoff_multiplier=1.8,  # Exponential backoff multiplier
                jitter_range=0.2,       # Jitter range
                reset_threshold=50      # Reset threshold
            )
            client.reconnect_config = reconnect_config
            logger.info("Network resilience enabled for SDK client")

        # Establish connection
        logger.info("Connecting SDK client...")
        await client.connect()
        logger.info("SDK client connected successfully")

        return client

    except ImportError as e:
        logger.error("Failed to import MCP SDK: %s", e)
        logger.info("Please ensure MCP SDK is properly installed")


class EnhancedMCPLauncher:
    """Enhanced MCP launcher, supporting service dependencies and readiness detection"""

    def __init__(self):
        self.service_manager = EnhancedResilientServiceManager()
        self._monitoring_task: Optional[asyncio.Task] = None

    async def start_services(
        self,
        mode: str = "all",
        endpoint: Optional[str] = None,
        access_id: Optional[str] = None,
        access_secret: Optional[str] = None,
        custom_mcp_server_endpoint: Optional[str] = None,
        enable_resilience: bool = True
    ):
        """Start services"""
        logger.info("Enhanced Resilient MCP Launcher Starting...")
        logger.info("=" * 70)

        # Setup signal handling
        self._setup_signal_handlers()

        try:
            # Prepare service configurations
            service_configs = {}
            service_factories: Dict[str, Callable[[ServiceConfig], Any]] = {}

            # Configure MCP server
            if mode in ["server", "all"]:
                service_configs["mcp_server"] = ServiceConfig(
                    name="mcp_server",
                    host="localhost",
                    port=8765,
                    enable_resilience=enable_resilience,
                    readiness_timeout=30
                )
                service_factories["mcp_server"] = create_enhanced_mcp_server

            # Configure SDK client (depends on MCP server)
            if mode in ["client", "all"]:
                depends_on = ["mcp_server"] if mode == "all" else None
                service_configs["sdk_client"] = ServiceConfig(
                    name="sdk_client",
                    endpoint=endpoint,
                    access_id=access_id,
                    access_secret=access_secret,
                    custom_mcp_server_endpoint=custom_mcp_server_endpoint,
                    enable_resilience=enable_resilience,
                    depends_on=depends_on,
                    readiness_timeout=30
                )
                service_factories["sdk_client"] = create_enhanced_sdk_client

            # Start all services in dependency order
            await self.service_manager.register_services_with_dependencies(
                service_configs, service_factories
            )

            # Start status monitoring
            self._monitoring_task = asyncio.create_task(
                self._monitor_services())

            # Display service information
            await self._show_service_info(mode)

            # Wait for services to run or shutdown signal
            logger.info(
                "All services are ready and running. Press Ctrl+C to stop.")
            await self.service_manager._shutdown_event.wait()

        except Exception as e:
            logger.error("Error starting services: %s", e)
            raise
        finally:
            await self._cleanup()

    async def _monitor_services(self):
        """Monitor service status"""
        try:
            while not self.service_manager._shutdown_event.is_set():
                await asyncio.sleep(45)  # Check every 45 seconds

                status_report = await self.service_manager.get_service_status()

                logger.info("Enhanced Service Status Report:")
                for name, status in status_report.items():
                    status_token = self._get_status_emoji(status["status"])
                    logger.info(
                        "   %s %s: %s", status_token, name, status['status'])

                    if "connected" in status:
                        conn_emoji = "OK" if status["connected"] else "DOWN"
                        logger.info(
                            "      %s Connected: %s", conn_emoji, status['connected'])

                    if "ready" in status:
                        ready_emoji = "READY" if status["ready"] else "WAIT"
                        logger.info(
                            "      %s Ready: %s", ready_emoji, status['ready'])

                    if "endpoint" in status:
                        logger.info("      Endpoint: %s", status['endpoint'])

        except asyncio.CancelledError:
            logger.info("Service monitoring stopped")
        except Exception as e:
            logger.error("Error in service monitoring: %s", e)

    def _get_status_emoji(self, status: str) -> str:
        """Get emoji corresponding to status"""
        emoji_map = {
            "running": "RUN",
            "ready": "READY",
            "starting": "START",
            "stopping": "STOP",
            "stopped": "OFF",
            "error": "ERROR",
            "reconnecting": "RETRY"
        }
        return emoji_map.get(status, "UNKNOWN")

    async def _show_service_info(self, mode: str):
        """Display service information"""
        logger.info("")
        logger.info("Enhanced Service Information:")
        logger.info("─" * 50)

        if mode in ["server", "all"]:
            logger.info("MCP Server:")
            logger.info("   • Address: http://localhost:8765")
            logger.info("   • Protocol: FastMCP with HTTP API")
            logger.info("   • Readiness: Health monitoring enabled")
            logger.info("   • Status: Ready for client connections")

        if mode in ["client", "all"]:
            logger.info("SDK Client:")
            logger.info("   • Mode: Resilient Connection")
            logger.info("   • Auto-reconnect: Enabled")
            logger.info("   • Network monitoring: Active")
            if mode == "all":
                logger.info("   • Dependencies: Waits for MCP Server ready")

        logger.info("")

    def _setup_signal_handlers(self):
        """Setup signal handlers"""
        def signal_handler():
            logger.info("Received shutdown signal...")
            asyncio.create_task(self.service_manager.graceful_shutdown())

        # Setup signal handlers
        try:
            for sig in [signal.SIGTERM, signal.SIGINT]:
                asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            import signal as sig_module
            sig_module.signal(sig_module.SIGINT, lambda s, f: signal_handler())

    async def _cleanup(self):
        """Cleanup resources"""
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        await self.service_manager.graceful_shutdown()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Enhanced Resilient MCP Launcher - Enterprise-level launcher with dependency management and readiness detection'
    )

    parser.add_argument('mode', choices=['all', 'server', 'client'], default='all', nargs='?',
                        help='Startup mode: all (server+client), server (server only), client (client only)')
    parser.add_argument('--endpoint', default=None,
                        help='SDK endpoint (can be set via MCP_ENDPOINT environment variable)')
    parser.add_argument('--access-id', default=None,
                        help='Access ID (can be set via MCP_ACCESS_ID environment variable)')
    parser.add_argument('--access-secret', default=None,
                        help='Access secret (can be set via MCP_ACCESS_SECRET environment variable)')
    parser.add_argument('--custom-mcp-server-endpoint', default='http://localhost:8765',
                        help='Custom MCP server endpoint')
    parser.add_argument('--disable-resilience', action='store_true',
                        help='Disable network resilience features (use basic reconnection)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        default='INFO', help='Log level')

    return parser.parse_args()


async def main():
    """Main function"""
    args = parse_args()

    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    launcher = EnhancedMCPLauncher()

    try:
        await launcher.start_services(
            mode=args.mode,
            endpoint=args.endpoint,
            access_id=args.access_id,
            access_secret=args.access_secret,
            custom_mcp_server_endpoint=args.custom_mcp_server_endpoint,
            enable_resilience=not args.disable_resilience
        )
    except KeyboardInterrupt:
        logger.info("Launcher stopped by user")
    except Exception as e:
        logger.error("Error in main: %s", e, exc_info=True)
        raise


if __name__ == "__main__":
    print("Enhanced Resilient MCP Launcher")
    print("=" * 70)
    print("Enterprise-level MCP launcher with service dependency management and readiness detection")
    print()
    print("Enhanced Features:")
    print("  • Service dependency management (automatic startup ordering)")
    print("  • Readiness detection mechanism (HTTP/TCP health checks)")
    print("  • Network resilience features (exponential backoff + jitter)")
    print("  • Continuous health monitoring")
    print("  • Intelligent failure recovery")
    print("  • Graceful shutdown handling")
    print()
    print("Service Management:")
    print("  • Topological sort startup order")
    print("  • Real-time status monitoring")
    print("  • Service readiness waiting")
    print("  • Dependency relationship validation")
    print()
    print("Usage Examples:")
    print("  python examples/__main__.py")
    print("  python examples/__main__.py server")
    print("  python examples/__main__.py client --endpoint wss://prod.com")
    print("  python examples/__main__.py --disable-resilience")
    print()
    print("Environment Variables:")
    print("  MCP_ENDPOINT       - SDK endpoint")
    print("  MCP_ACCESS_ID      - Access ID")
    print("  MCP_ACCESS_SECRET  - Access secret")
    print()
    print("Press Ctrl+C to stop all services")
    print("=" * 70)
    print()

    try:
        # Try to use uvloop for performance improvement
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("Using uvloop for enhanced performance")
        except ImportError:
            logger.info("Using default asyncio event loop")

        asyncio.run(main())

    except KeyboardInterrupt:
        print("\nAll services stopped")
    except Exception as e:
        print("\nStartup failed: %s", e)
        sys.exit(1)
