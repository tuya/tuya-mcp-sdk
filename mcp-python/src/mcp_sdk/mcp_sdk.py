"""
MCP SDK - Main Entry Point
Unified startup interface and management class
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Union

from .client import MCPSdkClient
from .exceptions import ConnectionError, MCPSdkError
from .models import MCPSdkRequest, MCPSdkResponse

logger = logging.getLogger(__name__)


@dataclass
class MCPClientConfig:
    """MCP client configuration"""

    server_endpoint: str
    server_params: Optional[Dict[str, Any]] = None
    timeout: int = 30
    headers: Optional[Dict[str, str]] = None
    headers_provider: Optional[Callable[[], Dict[str, str]]] = None


@dataclass
class MCPSdkConfig:
    """MCPSdk configuration"""

    endpoint: str
    access_id: str
    access_secret: str
    heartbeat_interval: int = 30
    reconnect_interval: int = 5
    max_reconnect_attempts: int = 5


class MCPSdk:
    """
    MCP SDK main entry class
    Provides unified startup, connection, and message handling interface
    """

    def __init__(
        self,
        mcpsdk_config: MCPSdkConfig,
        mcp_client_config: Optional[MCPClientConfig] = None,
        message_handler: Optional[
            Callable[[MCPSdkRequest], Union[MCPSdkResponse, None]]
        ] = None,
    ):
        """
        Initialize MCP SDK

        Args:
            mcpsdk_config: MCPSdk configuration
            mcp_client_config: MCP client configuration
            message_handler: Custom message handler
        """
        self.mcpsdk_config = mcpsdk_config
        self.mcp_client_config = mcp_client_config
        self.custom_message_handler = message_handler

        # Initialize client
        self.client: Optional[MCPSdkClient] = None
        self._running = False
        self._startup_complete = False

    async def startup(self):
        """
        Start MCPSdk connection

        Complete startup process:
        1. Initialize client
        2. HTTP request to get CID and Token
        3. Establish WebSocket connection
        4. Start heartbeat and message listening

        Raises:
            MCPSdkError: Raised when startup fails
        """
        # Check if already started
        if self._startup_complete:
            logger.debug("MCPSdk already started, skipping startup")
            return

        try:
            logger.info("Starting MCP SDK...")

            # 1. Initialize client
            custom_mcp_server_endpoint = None
            if self.mcp_client_config and self.mcp_client_config.server_endpoint:
                custom_mcp_server_endpoint = self.mcp_client_config.server_endpoint

            self.client = MCPSdkClient(
                endpoint=self.mcpsdk_config.endpoint,
                access_id=self.mcpsdk_config.access_id,
                access_secret=self.mcpsdk_config.access_secret,
                custom_mcp_server_endpoint=custom_mcp_server_endpoint,
                custom_mcp_server_params=(
                    self.mcp_client_config.server_params
                    if self.mcp_client_config
                    else None
                ),
                headers=(
                    self.mcp_client_config.headers if self.mcp_client_config else None
                ),
                headers_provider=(
                    self.mcp_client_config.headers_provider
                    if self.mcp_client_config
                    else None
                ),
                reconnect_config=None,
            )

            # Set custom message handler or default MCP forwarding handler
            if self.custom_message_handler:
                self.client.websocket_adapter.message_handler = (
                    self.custom_message_handler
                )
            elif self.mcp_client_config and self.mcp_client_config.server_endpoint:
                # Set default MCP forwarding handler
                self.client.websocket_adapter.message_handler = (
                    self.client.get_default_message_handler()
                )

            # 2. Connect to MCPSdk (including authentication and WebSocket connection)
            await self.client.connect()

            # 3. Start message listening
            self._running = True
            self._startup_complete = True

            logger.info("MCP SDK startup complete")

        except Exception as e:
            await self.shutdown()
            raise MCPSdkError(f"MCPSdk startup failed: {e}")

    async def run(self):
        """
        Run MCPSdk (blocking mode)
        Start listening for messages after startup, until manually stopped
        """
        if not self._startup_complete:
            await self.startup()

        if not self.client:
            raise MCPSdkError("Client not initialized")

        try:
            logger.info("MCP SDK is running...")
            await self.client.start_listening()
        except Exception as e:
            logger.error("Error while running MCPSdk: %s", e, exc_info=True)
            raise

    async def start_background(self):
        """
        Start MCPSdk in background mode
        Return immediately after startup, MCPSdk runs in background
        """
        if not self._startup_complete:
            await self.startup()

        if not self.client:
            raise MCPSdkError("Client not initialized")

        # Start background task
        asyncio.create_task(self.client.start_listening())
        logger.info("MCP SDK started in background")

    async def shutdown(self):
        """Close MCPSdk connection"""
        try:
            if self.client:
                await self.client.shutdown()
            logger.info("MCP SDK shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def send_mcp_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send MCP request

        Args:
            request: MCP request data

        Returns:
            MCP response data
        """
        if not self.client or not self._startup_complete:
            raise ConnectionError("MCPSdk not connected")

        return await self.client.send_request(request)

    async def send_response(self, response: MCPSdkResponse):
        """
        Send response message

        Args:
            response: MCPSdk response message
        """
        if not self.client or not self._startup_complete:
            raise ConnectionError("MCPSdk not connected")

        await self.client.websocket_adapter.send_message(response)

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return (
            self.client is not None
            and self._startup_complete
            and self.client.websocket_adapter.is_connected
        )

    @property
    def is_running(self) -> bool:
        """Check if running"""
        return self._running and self.is_connected

    # Context manager support
    async def __aenter__(self):
        """Async context manager entry"""
        await self.startup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.shutdown()


# Convenience function
def create_mcpsdk(
    endpoint: str,
    access_id: str,
    access_secret: str,
    custom_mcp_server_endpoint: Optional[str] = None,
    custom_mcp_server_params: Optional[Dict[str, Any]] = None,
    message_handler: Optional[
        Callable[[MCPSdkRequest], Union[MCPSdkResponse, None]]
    ] = None,
    **kwargs,
) -> MCPSdk:
    """
    Convenience function: Create and start MCPSdk

    Args:
        endpoint: MCPSdk domain
        access_id: Access ID
        access_secret: Access Secret
        custom_mcp_server_endpoint: Custom MCP server endpoint
        custom_mcp_server_params: Custom MCP server parameters
        message_handler: Message handler
        **kwargs: Other configuration parameters

    Returns:
        Started MCPSdk instance
    """

    # Build configuration
    mcpsdk_config = MCPSdkConfig(
        endpoint=endpoint,
        access_id=access_id,
        access_secret=access_secret,
        **{
            k: v
            for k, v in kwargs.items()
            if k
            in ["heartbeat_interval", "reconnect_interval", "max_reconnect_attempts"]
        },
    )

    mcp_client_config = None
    if custom_mcp_server_endpoint:
        mcp_client_config = MCPClientConfig(
            server_endpoint=custom_mcp_server_endpoint,
            server_params=custom_mcp_server_params,
            headers=kwargs.get("headers"),
            headers_provider=kwargs.get("headers_provider"),
        )

    # Create MCPSdk (startup will be called in __aenter__)
    mcpsdk = MCPSdk(
        mcpsdk_config=mcpsdk_config,
        mcp_client_config=mcp_client_config,
        message_handler=message_handler,
    )

    return mcpsdk


# Sync function wrapper
def run_mcpsdk(
    endpoint: str,
    access_id: str,
    access_secret: str,
    custom_mcp_server_endpoint: Optional[str] = None,
    custom_mcp_server_params: Optional[Dict[str, Any]] = None,
    message_handler: Optional[
        Callable[[MCPSdkRequest], Union[MCPSdkResponse, None]]
    ] = None,
    **kwargs,
):
    """
    Run MCPSdk synchronously

    Args:
        endpoint: MCPSdk domain
        access_id: Access ID
        access_secret: Access Secret
        custom_mcp_server_endpoint: Custom MCP server endpoint
        custom_mcp_server_params: Custom MCP server parameters
        message_handler: Message handler
        **kwargs: Other configuration parameters
    """

    async def _run():
        async with create_mcpsdk(
            endpoint=endpoint,
            access_id=access_id,
            access_secret=access_secret,
            custom_mcp_server_endpoint=custom_mcp_server_endpoint,
            custom_mcp_server_params=custom_mcp_server_params,
            message_handler=message_handler,
            **kwargs,
        ) as mcpsdk:
            await mcpsdk.run()

    asyncio.run(_run())
