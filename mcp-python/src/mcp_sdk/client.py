"""
MCP SDK Client - Main client class
"""

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from .auth import AuthManager
from .connection_manager import ReconnectConfig
from .exceptions import ConnectionError, MCPSdkError
from .mcp_client import MCPClientManager
from .models import AuthConfig, MCPSdkRequest, MCPSdkResponse, TokenData
from .websocket_adapter import WebSocketAdapter

logger = logging.getLogger(__name__)


class MCPSdkClient:
    """MCP SDK client for connecting to MCP SDK services"""

    def __init__(
        self,
        endpoint: str,
        access_id: str,
        access_secret: str,
        custom_mcp_server_endpoint: Optional[str] = None,
        reconnect_config: Optional[ReconnectConfig] = None,
        custom_mcp_server_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        headers_provider: Optional[
            Callable[[], Union[Dict[str, str], Awaitable[Dict[str, str]], None]]
        ] = None,
    ):
        """
        Initialize MCP SDK client

        Args:
            endpoint: SDK domain
            access_id: Developer access ID
            access_secret: access secret
            custom_mcp_server_endpoint: Custom MCP server endpoint
        """
        self.config = AuthConfig(
            endpoint=endpoint,
            access_id=access_id,
            access_secret=access_secret,
        )

        self.is_ready = False
        self.ready_event = asyncio.Event()

        # Initialize components
        self.auth_manager = AuthManager(self.config)

        if reconnect_config is None:
            reconnect_config = ReconnectConfig(
                base_interval=1.0,
                max_interval=120.0,
                max_retries=-1,
                backoff_multiplier=2.0,
                jitter_range=0.1,
                reset_threshold=100,
            )

        self.reconnect_config = reconnect_config

        self.websocket_adapter = WebSocketAdapter(
            endpoint=endpoint,
            access_id=access_id,
            access_secret=access_secret,
            message_handler=self._handle_sdk_request,
            token_provider=self._get_token_for_reconnect,
            reconnect_config=self.reconnect_config,
        )

        self.mcp_client_manager: Optional[MCPClientManager] = None
        if custom_mcp_server_endpoint:
            self.mcp_client_manager = MCPClientManager(
                custom_mcp_server_endpoint,
                reconnect_config=reconnect_config,
                headers=headers,
                headers_provider=headers_provider,
            )

        self._connected = False
        self._running = False

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()

    async def connect(self):
        """Connect to SDK"""
        try:
            logger.info("Connecting to MCP SDK...")

            # 1. Authenticate and get token
            async with self.auth_manager:
                token_data = await self.auth_manager.get_token()

            # 2. Connect to MCP server (if configured)
            if self.mcp_client_manager:
                await self.mcp_client_manager.connect()

            # 3. Establish WebSocket connection
            await self.websocket_adapter.connect(token_data)

            self.is_ready = True
            self.ready_event.set()

            self._connected = True
            logger.info("MCP SDK connection successful")

        except Exception as e:
            await self.disconnect()
            raise MCPSdkError(f"Failed to connect to SDK: {e}")

    async def disconnect(self):
        """Disconnect"""
        try:
            self.is_ready = False
            self.ready_event.clear()

            self._connected = False
            self._running = False

            # Close WebSocket connection
            await self.websocket_adapter.close()

            # Disconnect from MCP server
            if self.mcp_client_manager:
                await self.mcp_client_manager.disconnect()

            logger.info("MCP SDK connection disconnected")

        except Exception as e:
            logger.error("Error occurred while disconnecting: %s", e)

    async def shutdown(self):
        """Shutdown client"""
        try:
            self._connected = False
            self._running = False

            # Close WebSocket connection
            await self.websocket_adapter.shutdown()

            # Disconnect from MCP server
            if self.mcp_client_manager:
                await self.mcp_client_manager.disconnect()

            logger.info("MCP SDK connection shutdown")

        except Exception as e:
            logger.error("Error occurred while disconnecting: %s", e)

    async def start_listening(self):
        """Start listening for messages"""
        self._running = True
        logger.info("Started listening for SDK messages")

        # Use new adapter to start listening
        await self.websocket_adapter.start_listening()

    async def send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send MCP request

        Args:
            request: MCP request data

        Returns:
            MCP response data

        Raises:
            MCPSdkError: Request sending failed
        """
        if not self._connected:
            raise ConnectionError("Client not connected")

        if not self.mcp_client_manager:
            raise MCPSdkError("MCP client not configured")

        try:
            method = request.get("method")
            if not isinstance(method, str) or not method:
                raise MCPSdkError("Request missing required 'method' field")

            ts = str(int(time.time() * 1000))

            # Build SDK request
            sdk_request = MCPSdkRequest(
                request_id=f"req_{ts}",
                endpoint="",
                version="v1",
                method=method,
                ts=ts,
                request=json.dumps(request, separators=(",", ":"), ensure_ascii=False),
                sign=None,
            )

            # Send request through MCP client
            response = await self.mcp_client_manager.send_request(sdk_request)

            # Response body is JSON string (best-effort parse)
            try:
                parsed = json.loads(response.response)
                if isinstance(parsed, dict):
                    return parsed
                return {"data": parsed}
            except Exception:
                return {"raw": response.response}

        except Exception as e:
            raise MCPSdkError(f"Failed to send request: {e}") from e

    async def _handle_sdk_request(self, request: MCPSdkRequest) -> MCPSdkResponse:
        """
        Handle SDK request

        Args:
            request: SDK request

        Returns:
            SDK response
        """
        logger.debug("Handling SDK request: %s", request.request_id)

        try:
            if not self.mcp_client_manager:
                error_string = json.dumps(
                    {"error": "MCP client not configured"},
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                return MCPSdkResponse(
                    request_id=request.request_id,
                    endpoint=request.endpoint,
                    version=request.version,
                    method=request.method,
                    ts=str(int(time.time() * 1000)),
                    response=error_string,
                    sign=None,
                )

            # Process request through MCP client
            response = await self.mcp_client_manager.send_request(request)
            return response

        except Exception as e:
            logger.error("Failed to handle SDK request: %s", e)
            error_string = json.dumps(
                {"error": str(e)}, separators=(",", ":"), ensure_ascii=False
            )
            return MCPSdkResponse(
                request_id=request.request_id,
                endpoint=request.endpoint,
                version=request.version,
                method=request.method,
                ts=str(int(time.time() * 1000)),
                response=error_string,
                sign=None,
            )

    def set_mcp_server(
        self,
        mcp_server_endpoint: str,
        server_params: Optional[Dict[str, Any]] = None,
    ):
        """Set MCP server URI"""
        headers: Optional[Dict[str, str]] = None
        headers_provider: Optional[
            Callable[[], Union[Dict[str, str], Awaitable[Dict[str, str]], None]]
        ] = None
        if server_params:
            headers = server_params.get("headers")
            headers_provider = server_params.get("headers_provider")

        self.mcp_client_manager = MCPClientManager(
            mcp_server_endpoint,
            reconnect_config=self.reconnect_config,
            headers=headers,
            headers_provider=headers_provider,
        )

    def get_default_message_handler(self):
        """Get the default message handler for SDK requests"""
        return self._handle_sdk_request

    async def _get_token_for_reconnect(self) -> Optional[TokenData]:
        """Get token for reconnection (force refresh)"""
        try:
            logger.info("Starting token acquisition for reconnection...")
            async with self.auth_manager:
                logger.info("AuthManager session created, requesting token...")
                token_data = await self.auth_manager.get_token(force_refresh=True)
                if token_data:
                    logger.info(
                        "Token acquired successfully for reconnection, client_id: %s",
                        token_data.client_id,
                    )
                else:
                    logger.error("Token acquisition returned None")
                return token_data
        except Exception as e:
            logger.error("Failed to get token for reconnection: %s", e, exc_info=True)
            return None

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected and self.websocket_adapter.is_connected

    @property
    def is_running(self) -> bool:
        """Check if running - comprehensive running status check"""
        # Must satisfy both running flag and connection status
        return self._running and self.is_connected
