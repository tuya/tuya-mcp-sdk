"""
WebSocket Adapter for MCP SDK
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Dict, Any, Union, Awaitable
from urllib.parse import quote, urlparse

# Try to import websockets with fallback
try:
    import websockets
    from websockets.asyncio.client import ClientConnection
    from websockets.exceptions import ConnectionClosed, WebSocketException
    from websockets import ConnectionState
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    # Fallback for when websockets is not available
    WEBSOCKETS_AVAILABLE = False
    ClientConnection = None
    ConnectionClosed = Exception
    WebSocketException = Exception
    ConnectionState = None

# Try to import pydantic with fallback
try:
    from pydantic import ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    # Fallback for when pydantic is not available
    PYDANTIC_AVAILABLE = False
    ValidationError = Exception

from .models import MCPSdkRequest, MCPSdkResponse, TokenData
from .signature import SignatureUtils
from .connection_manager import ConnectionManager, ReconnectConfig
from .exceptions import ConnectionError

logger = logging.getLogger(__name__)


class WebSocketAdapter:
    """WebSocket Adapter"""

    def __init__(
        self,
        endpoint: str,
        access_id: str,
        access_secret: str,
        message_handler: Optional[Callable[[
            MCPSdkRequest], Union[MCPSdkResponse, Awaitable[MCPSdkResponse], None]]] = None,
        token_provider: Optional[Callable[[], Optional[TokenData]]] = None,
        reconnect_config: Optional[ReconnectConfig] = None
    ):

        self.endpoint = endpoint
        self.access_id = access_id
        self.access_secret = access_secret
        self.message_handler = message_handler
        self.token_provider = token_provider

        self._websocket: Optional[ClientConnection] = None
        self._token_data: Optional[TokenData] = None
        self._running = False
        self._heartbeat_manager = None

        # Use new connection manager
        self._connection_manager = ConnectionManager(reconnect_config)
        self._connection_manager.set_connector(self._establish_connection)
        self._connection_manager.set_network_checker(
            self._check_network_connectivity)  # type: ignore
        self._connection_manager.add_state_change_callback(
            self._on_connection_state_change)
        self._connection_manager.add_network_change_callback(
            self._on_network_change)

    def set_heartbeat_manager(self, heartbeat_manager):
        """Set heartbeat manager reference"""
        self._heartbeat_manager = heartbeat_manager
        if self._heartbeat_manager:
            self._heartbeat_manager.set_connection_failure_callback(
                self._on_heartbeat_failure)

    async def connect(self, token_data: TokenData) -> bool:
        """
        Establish WebSocket connection

        Args:
            token_data: Authentication token data

        Returns:
            Connection success or failure
        """
        self._token_data = token_data
        return await self._connection_manager.connect()

    async def _establish_connection(self):
        """
        Actual WebSocket connection establishment logic
        """
        if not self._token_data:
            raise ConnectionError("Token data not available")

        try:
            await self._refresh_token_for_reconnect()
            # Build WebSocket URL with cid as query parameter
            ws_url = f"{self.endpoint.rstrip('/')}/ws/mcp"
            if ws_url.startswith('http'):
                ws_url = ws_url.replace('http', 'ws', 1)
            elif not ws_url.startswith('ws'):
                ws_url = f"ws://{ws_url}"  # Use ws:// for local testing

            # Add cid as query parameter
            ws_url = f"{ws_url}?client_id={quote(self._token_data.client_id)}"

            # Create connection headers
            headers = self._create_connection_headers()

            # Establish WebSocket connection
            self._websocket = await websockets.connect(
                ws_url,
                additional_headers=headers,
                ping_interval=30,
                ping_timeout=10,
                max_size=2**20,  # 1MB max message size
                compression=None,  # Disable compression for better performance
                proxy=None
            )

            logger.info("[MCP-SDK] WebSocket connection established successfully! Client ID: %s",
                        self._token_data.client_id)

        except Exception as e:
            err_msg = f"WebSocket connection failed: {e}"
            logger.error(err_msg)
            raise ConnectionError(err_msg)

    def _create_connection_headers(self) -> Dict[str, str]:
        """Create connection headers"""
        if not self._token_data:
            raise ConnectionError("Token data not set")

        return SignatureUtils.create_websocket_headers(
            access_id=self.access_id,
            access_secret=self._token_data.token,
            client_id=self._token_data.client_id,
            path="/ws/mcp"
        )

    async def start_listening(self):
        """Start listening for messages"""
        self._running = True
        logger.info("[MCP-SDK] Started listening for WebSocket messages...")

        # Start network monitoring for connection manager
        await self._connection_manager.start_monitoring()

        # Start heartbeat monitoring task
        heartbeat_task = None
        if self._heartbeat_manager:
            heartbeat_task = asyncio.create_task(self._monitor_heartbeat())
            logger.info("[MCP-SDK] Heartbeat monitoring started")

        try:
            while self._running:
                try:
                    # Wait for connection to be ready
                    if not self._connection_manager.is_connected:
                        await asyncio.sleep(1)
                        continue

                    if not self._websocket:
                        await asyncio.sleep(1)
                        continue

                    # Listen for messages
                    async for message in self._websocket:
                        if not self._running:
                            break

                        try:
                            await self._handle_message(message)
                        except Exception as e:
                            logger.error("Error handling message: %s", e)

                except ConnectionClosed:
                    logger.warning("[MCP-SDK] WebSocket connection closed")
                    self._websocket = None
                    self._connection_manager.trigger_reconnect(
                        "Connection closed")
                except WebSocketException as e:
                    logger.error("[MCP-SDK] WebSocket error: %s", e)
                    self._websocket = None
                    self._connection_manager.trigger_reconnect(
                        f"WebSocket error: {e}")
                except Exception as e:
                    logger.error(
                        "[MCP-SDK] Unexpected error: %s", e, exc_info=True)
                    self._connection_manager.trigger_reconnect(
                        f"Unexpected error: {e}")

                # Brief pause before retrying
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.debug("WebSocket listening cancelled")
        finally:
            # Stop heartbeat monitoring task
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            # Stop connection manager
            await self._connection_manager.stop_monitoring()

    def _on_connection_state_change(self, _old_state: ConnectionState, new_state: ConnectionState):
        """Connection state change callback"""
        # When connection is successful, restart heartbeat manager
        if new_state == ConnectionState.CONNECTED and self._heartbeat_manager:
            asyncio.create_task(self._restore_heartbeat_manager())

    def _on_network_change(self, is_available: bool):
        """Network state change callback"""
        if is_available:
            logger.info("Network recovered")
        else:
            logger.warning("Network unavailable")

    async def _check_network_connectivity(self) -> Optional[bool]:
        """Check network connectivity"""
        try:

            # Extract hostname from endpoint
            parsed = urlparse(self.endpoint)
            host = parsed.hostname or parsed.netloc.split(':')[0]
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)

            # Try TCP connection test
            future = asyncio.open_connection(host, port)
            try:
                _, writer = await asyncio.wait_for(future, timeout=5)
                writer.close()
                await writer.wait_closed()
                return True
            except (asyncio.TimeoutError, OSError, ConnectionError):
                return None

        except Exception as e:
            logger.debug("Network connectivity check error: %s", e)
            return None  # If detection fails, assume network is available to avoid blocking reconnection

    async def _monitor_heartbeat(self):
        """Heartbeat monitoring"""
        try:
            while self._running:
                # Check heartbeat status every 5 seconds
                await asyncio.sleep(5)

                if not self._running:
                    break

                # Check if heartbeat manager is still running
                if self._heartbeat_manager and not self._heartbeat_manager.is_running:
                    logger.warning(
                        "Heartbeat manager stopped, connection may be lost")
                    self._connection_manager.trigger_reconnect(
                        "Heartbeat failure")

        except asyncio.CancelledError:
            logger.debug("Heartbeat monitoring cancelled")
        except Exception as e:
            logger.error("Error in heartbeat monitoring: %s", e, exc_info=True)

    async def _on_heartbeat_failure(self, error):
        """Heartbeat failure processing callback"""
        try:
            logger.warning("Heartbeat failure detected: %s", error)
            self._connection_manager.trigger_reconnect(
                f"Heartbeat failure: {error}")
        except Exception as e:
            logger.error("Error in heartbeat failure handler: %s",
                         e, exc_info=True)

    async def _handle_message(self, message: str):
        """Handle received message"""
        try:
            data = json.loads(message)

            # Notify heartbeat manager that message received
            if self._heartbeat_manager:
                self._heartbeat_manager.on_websocket_message()

            # Check if it's a sys/error method
            if "method" in data and data.get("method") == "sys/error":
                logger.warning("Received sys/error message: %s", data)
                return

            # Perform signature verification
            if not self._verify_message_signature(data):
                logger.error("Message signature verification failed: %s", data)
                return

            # Check if it's a new format SDK request
            if "request_id" in data and "request" in data:
                try:
                    # Convert new format to format expected by MCPSdkRequest
                    converted_data = {
                        "request_id": data["request_id"],
                        "endpoint": data.get("endpoint", ""),
                        "version": data.get("version", "1.0"),
                        "method": data.get("method", ""),
                        "ts": data.get("ts", str(int(asyncio.get_event_loop().time() * 1000))),
                        "request": data["request"]
                    }

                    # Parse as SDK request
                    request = MCPSdkRequest(**converted_data)
                    logger.info(
                        "[MCP-SDK] Received request: %s (ID: %s)", request.method, request.request_id)

                    # Call message handler
                    if self.message_handler:
                        response = await self._call_message_handler(request)
                        if response:
                            await self._send_response(response, original_request_data=data)
                        else:
                            logger.info(
                                "[MCP-SDK] No response required for request: %s", request.request_id)
                    else:
                        logger.warning(
                            "No message handler set, ignoring request")
                    return

                except (json.JSONDecodeError, KeyError) as e:
                    logger.error("Failed to parse new format request: %s", e)
                    return

            else:
                logger.debug("Ignoring non-request message: %s", data)
                return

        except json.JSONDecodeError as e:
            logger.error("JSON parsing failed: %s", e)
        except ValidationError as e:
            if PYDANTIC_AVAILABLE:
                logger.error("Message validation failed: %s", e)
            else:
                logger.error(
                    "Message validation failed (pydantic not available): %s", e)
        except Exception as e:
            logger.error("Message handling failed: %s", e)

    def _verify_message_signature(self, data: Dict[str, Any]) -> bool:
        """Verify message signature"""
        try:
            if "sign" not in data:
                logger.warning("Message missing signature field")
                return False

            if not self._token_data:
                logger.error(
                    "Token data not available for signature verification")
                return False

            is_valid = SignatureUtils.verify_message_signature(
                access_secret=self._token_data.token,
                message_data=data
            )

            if not is_valid:
                logger.error("Message signature verification failed")
                return False

            logger.debug("Message signature verification successful")
            return True

        except Exception as e:
            logger.error("Error during signature verification: %s", e)
            return False

    async def _call_message_handler(self, request: MCPSdkRequest) -> Optional[MCPSdkResponse]:
        """Call message handler"""
        try:
            method = request.method

            if method == "root/migrate":
                logger.info(
                    "Received root/migrate request, initiating reconnection")
                asyncio.create_task(self._handle_migrate_reconnect())
                return None

            elif method == "root/kickout":
                logger.warning(
                    "Received root/kickout request, terminating connection")
                asyncio.create_task(self._handle_kickout())
                return None

            if not self.message_handler:
                logger.warning("No message handler set, ignoring request")
                return None

            # Handle normal requests
            if asyncio.iscoroutinefunction(self.message_handler):
                return await self.message_handler(request)
            else:
                ret = self.message_handler(request)
                if ret is not None and isinstance(ret, MCPSdkResponse):
                    return ret
                else:
                    return MCPSdkResponse(
                        request_id=request.request_id,
                        endpoint=request.endpoint,
                        version=request.version,
                        method=request.method,
                        ts=str(int(asyncio.get_event_loop().time() * 1000)),
                        response=None
                    )

        except Exception as e:
            logger.error("Message handler execution failed: %s", e)
            error_string = json.dumps(
                {"error": str(e)}, separators=(',', ':'), ensure_ascii=False)
            return MCPSdkResponse(
                request_id=request.request_id,
                endpoint=request.endpoint,
                version=request.version,
                method=request.method,
                ts=str(int(asyncio.get_event_loop().time() * 1000)),
                response=error_string
            )

    async def _send_response(self, response: MCPSdkResponse, original_request_data: Optional[Dict[str, Any]] = None):
        """Send response"""

        if not original_request_data:
            logger.warning(
                "No original request data available, skipping response")
            return

        try:
            response_dict = response.model_dump()

            new_format_response = {
                "request_id": original_request_data["request_id"],
                "endpoint": original_request_data.get("endpoint", ""),
                "version": original_request_data.get("version", "1.0.0"),
                "method": original_request_data.get("method", ""),
                "ts": str(int(asyncio.get_event_loop().time() * 1000)),
                "response": response_dict["response"]
            }

            if not self._token_data:
                logger.error("Token data not available for response signing")
                return

            # Sign response and add sign field
            signed_dict = SignatureUtils.sign_message(
                self._token_data.token, new_format_response)
            new_format_response["sign"] = signed_dict["sign"]

            message = json.dumps(new_format_response, ensure_ascii=False)

            # Send response through WebSocket
            if self._websocket:
                await self._websocket.send(message)
                logger.info(
                    "[MCP-SDK] Response sent: %s, message: %s", response.request_id, message)
            else:
                logger.error("WebSocket connection not available")

        except Exception as e:
            logger.error("Failed to send response: %s", e)

    async def _handle_migrate_reconnect(self):
        """Handle migrate reconnection request"""
        try:
            logger.info("Handling migrate reconnection...")
            self._connection_manager.trigger_reconnect("Migration request")
        except Exception as e:
            logger.error("Error during migrate reconnection: %s", e)

    async def _handle_kickout(self):
        """Handle kickout request"""
        try:
            logger.warning("Handling kickout request - terminating connection")
            await self._connection_manager.shutdown()
            self._running = False

            if self._heartbeat_manager:
                self._heartbeat_manager.mark_service_offline()

            logger.info("Service marked as offline due to kickout")

        except Exception as e:
            logger.error("Error during kickout handling: %s", e)

    async def _restore_heartbeat_manager(self):
        """Restore heartbeat manager after successful reconnection"""
        try:
            if self._heartbeat_manager and self._websocket:
                logger.info("Restoring heartbeat manager after reconnection")
                self._heartbeat_manager.set_websocket(self._websocket)
                if not self._heartbeat_manager.is_running:
                    await self._heartbeat_manager.start()
                    logger.info(
                        "Heartbeat manager restarted after reconnection")
        except Exception as e:
            logger.error("Failed to restore heartbeat manager: %s", e)

    async def _refresh_token_for_reconnect(self) -> Optional[TokenData]:
        """Refresh token for reconnection"""
        try:
            if self.token_provider:
                logger.info("Refreshing token for reconnection...")
                if asyncio.iscoroutinefunction(self.token_provider):
                    new_token_data = await self.token_provider()
                else:
                    new_token_data = self.token_provider()

                if new_token_data:
                    self._token_data = new_token_data
                    logger.info("Token refreshed successfully for reconnection, client_id: %s",
                                new_token_data.client_id)
                    return new_token_data
                else:
                    logger.error("Token provider returned None")
                    return None
            else:
                logger.warning("No token provider available")
                return self._token_data
        except Exception as e:
            logger.error(
                "Failed to refresh token for reconnection: %s", e, exc_info=True)
            return None

    async def send_message(self, message: MCPSdkResponse, original_request_data: Optional[Dict[str, Any]] = None):
        """Send message to WebSocket"""
        if not self._connection_manager.is_connected:
            raise ConnectionError("WebSocket connection not established")

        await self._send_response(message, original_request_data)

    async def close(self):
        """Close connection"""
        await self._connection_manager.disconnect()

        if self._websocket:
            try:
                await self._websocket.close()
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error("Error closing WebSocket: %s", e)
            finally:
                self._websocket = None

    async def shutdown(self):
        """Shutdown connection"""
        self._running = False
        await self._connection_manager.shutdown()

        if self._websocket:
            await self._websocket.close()
            self._websocket = None

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connection_manager.is_connected and self._websocket is not None

    @property
    def connection_state(self) -> ConnectionState:
        """Get connection state"""
        return self._connection_manager.state
