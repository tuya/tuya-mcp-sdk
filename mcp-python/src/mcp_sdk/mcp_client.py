"""MCP Client Manager for handling MCP server connections using FastMCP."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from logging import Handler, LogRecord
from typing import Any, cast

# Try to import fastmcp, fallback to placeholder if not available
try:
    import httpx
    from fastmcp import Client
    from fastmcp.client.transports import (
        SSETransport,
        StreamableHttpTransport,
    )

    FASTMCP_AVAILABLE = True
except ImportError:
    # Fallback Client class for when fastmcp is not available
    raise ImportError("fastmcp not installed")

from .connection_manager import ConnectionManager, ConnectionState, ReconnectConfig
from .exceptions import MCPClientError
from .models import MCPSdkRequest, MCPSdkResponse

logger = logging.getLogger(__name__)


class SSEErrorLogHandler(Handler):
    """Log handler to capture SSE errors from FastMCP"""

    def __init__(self, mcp_client_manager: MCPClientManager):
        super().__init__()
        self.mcp_client_manager = mcp_client_manager
        self.setLevel(logging.ERROR)

    def emit(self, record: LogRecord):
        """Capture log records from mcp.client.sse"""
        try:
            if record.name == "mcp.client.sse" and record.levelno >= logging.ERROR:
                error_msg = record.getMessage()
                if "sse_reader" in error_msg.lower():
                    logger.warning("SSE error detected via logs: %s", error_msg)
                    # Trigger reconnect
                    if (
                        self.mcp_client_manager
                        and self.mcp_client_manager._connection_manager
                    ):
                        self.mcp_client_manager._connection_errors += 1
                        self.mcp_client_manager._connection_manager.trigger_reconnect(
                            "SSE error detected"
                        )
        except Exception:
            pass  # Don't let handler errors affect the application


class MCPClientManager:
    """MCP client manager using FastMCP Client for handling connections to MCP servers"""

    def __init__(
        self,
        mcp_server_endpoint: str,
        reconnect_config: ReconnectConfig | None = None,
        headers: dict[str, str] | None = None,
        headers_provider: Callable[
            [], dict[str, str] | Awaitable[dict[str, str]] | None
        ]
        | None = None,
        timeout: int = 630,
    ):
        self.mcp_server_endpoint = mcp_server_endpoint
        self.timeout = timeout  # Default 5 minutes for SSE connections
        # NOTE: fastmcp.Client is generic and invariant in its transport type.
        # Our client may be created from multiple transports (SSE/streamable-http
        # and stdio inferred from strings/paths). Use Any to avoid false positives
        # while keeping runtime behavior unchanged.
        self._client: Client[Any] | None = None
        self._connected = False
        self._health_check_task: asyncio.Task[None] | None = None
        self._client_monitor_task: asyncio.Task[None] | None = None
        self._last_successful_request = time.time()
        self._connection_errors = 0  # Track consecutive connection errors
        self._client_error: Exception | None = None  # Track client errors

        self._headers: dict[str, str] | None = headers
        self._headers_provider = headers_provider
        self._resolved_headers: dict[str, str] | None = None

        # Use connection manager with enhanced reconnect config for SSE
        if reconnect_config is None:
            reconnect_config = ReconnectConfig(
                base_interval=2.0,  # Start with 2 seconds
                # Max 30 seconds between retries (faster recovery)
                max_interval=30.0,
                max_retries=20,  # Limit to 20 retries to prevent infinite loops
                backoff_multiplier=1.3,  # Gentler backoff
                jitter_range=0.2,  # Add some randomness
                reset_threshold=5,  # Reset after 5 successful connections
            )

        self._connection_manager = ConnectionManager(reconnect_config)
        self._connection_manager.set_connector(self._establish_connection)
        self._connection_manager.set_network_checker(
            self._check_network_connectivity_sync
        )
        self._connection_manager.add_state_change_callback(
            self._on_connection_state_change
        )

        # Install SSE error log handler
        self._log_handler = None
        self._install_sse_log_handler()

    async def connect(self, max_initial_retry: int = 3, initial_timeout: float = 60.0):
        """
        Connect to MCP server with retry logic

        Args:
            max_initial_retry: Maximum number of initial connection attempts
            initial_timeout: Total timeout for initial connection attempts

        Returns:
            True if connected successfully

        Raises:
            MCPClientError: If connection fails after all retries
        """
        logger.info(
            "MCPClientManager.connect() called (max_retry=%d, timeout=%.1fs)",
            max_initial_retry,
            initial_timeout,
        )

        start_time = time.time()
        last_error = None

        for attempt in range(1, max_initial_retry + 1):
            # Check if we've exceeded total timeout
            elapsed = time.time() - start_time
            if elapsed >= initial_timeout:
                logger.error("Initial connection timeout after %.1fs", elapsed)
                break

            try:
                logger.info("Connection attempt #%d/%d", attempt, max_initial_retry)
                result = await self._connection_manager.connect()

                if result:
                    logger.info(
                        "MCP client connected successfully on attempt #%d", attempt
                    )
                    return True
                else:
                    logger.warning("Connection attempt #%d failed", attempt)
                    last_error = "Connection returned False"

            except Exception as e:
                logger.warning("Connection attempt #%d failed: %s", attempt, e)
                last_error = str(e)

            # Wait before retry (exponential backoff)
            if attempt < max_initial_retry:
                wait_time = min(2.0**attempt, 10.0)  # Max 10 seconds
                logger.info("Waiting %.1fs before retry...", wait_time)
                await asyncio.sleep(wait_time)

        # All retries failed - trigger background reconnection but don't block startup
        error_msg = (
            f"Failed to connect after {max_initial_retry} attempts: {last_error}"
        )
        logger.error("%s", error_msg)
        logger.info("Starting background reconnection mechanism...")
        self._connection_manager.trigger_reconnect("Initial connection failed")

        # Don't raise exception - allow service to start and keep trying in background
        return False

    async def _cleanup_client(self):
        """Clean up current client connection"""
        try:
            if self._client:
                try:
                    await self._client.__aexit__(None, None, None)
                except Exception as e:
                    logger.debug("Error during client cleanup: %s", e)
                self._client = None
            self._connected = False
        except Exception as e:
            logger.error("Error in _cleanup_client: %s", e)
            self._client = None
            self._connected = False

    def _is_unauthorized(self, exc: Exception) -> bool:
        """Return True if an exception represents HTTP 401 Unauthorized."""
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code == 401
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return status == 401

    async def _resolve_headers(self) -> dict[str, str] | None:
        """Resolve headers for the current (re)connect attempt."""
        merged: dict[str, str] = dict(self._headers or {})

        if not self._headers_provider:
            return merged or None

        try:
            provided = self._headers_provider()
            if asyncio.iscoroutine(provided):
                provided = await provided
        except Exception as e:
            logger.warning("headers_provider failed: %s", e)
            return merged or None

        if not provided:
            return merged or None

        if not isinstance(provided, dict):
            logger.warning("headers_provider returned non-dict: %s", type(provided))
            return merged or None

        merged.update(provided)
        return merged

    async def _establish_connection(self):
        """Actually establish MCP server connection"""
        connection_start_time = time.time()

        # Clean up any existing connection first
        await self._cleanup_client()

        try:
            logger.info("Connecting to MCP server: %s", self.mcp_server_endpoint)

            # Resolve headers for this connection attempt (including reconnects)
            self._resolved_headers = await self._resolve_headers()

            # Create FastMCP Client
            if self.mcp_server_endpoint.startswith(("http://", "https://")):
                self._client = Client(
                    transport=self._create_transport(), timeout=self.timeout
                )
            else:
                self._client = Client(
                    transport=self.mcp_server_endpoint, timeout=self.timeout
                )

            if not self._client:
                raise MCPClientError("MCP client not available")

            # Connect to the MCP server with timeout
            connection_timeout = min(60, self.timeout)
            await asyncio.wait_for(
                self._client.__aenter__(), timeout=connection_timeout
            )

            connection_time = time.time() - connection_start_time
            self._connected = True
            self._last_successful_request = time.time()
            self._connection_errors = 0
            self._client_error = None
            logger.info("MCP server connected (took %.2fs)", connection_time)

            # Start client monitor to detect background errors
            self._start_client_monitor()

        except asyncio.TimeoutError as e:
            connection_time = time.time() - connection_start_time
            await self._cleanup_client()
            logger.warning("Connection timeout after %.2fs", connection_time)
            raise MCPClientError(
                f"Connection timeout after {connection_time:.1f}s"
            ) from e

        except Exception as e:
            connection_time = time.time() - connection_start_time
            await self._cleanup_client()

            if self._is_unauthorized(e):
                logger.warning(
                    "MCP server unauthorized (HTTP 401) during connect (%.2fs)",
                    connection_time,
                )
                self._connection_manager.trigger_reconnect("HTTP 401 Unauthorized")
                raise MCPClientError("HTTP 401 Unauthorized") from e

            # Log error with appropriate level
            error_str = str(e).lower()
            if any(
                err in error_str
                for err in ["502", "503", "504", "refused", "reset", "unavailable"]
            ):
                logger.warning(
                    "Connection failed (%.2fs): %s - Server may not be ready",
                    connection_time,
                    e,
                )
            else:
                logger.error("Connection failed (%.2fs): %s", connection_time, e)

            raise MCPClientError(f"Failed to connect: {e}") from e

    def _on_connection_state_change(
        self, old_state: ConnectionState, new_state: ConnectionState
    ):
        """Connection state change callback"""
        try:
            if not isinstance(new_state, ConnectionState) or not isinstance(
                old_state, ConnectionState
            ):
                logger.error("Invalid connection state parameters")
                return

            logger.info("Connection state: %s -> %s", old_state.value, new_state.value)

            # Start monitoring when connected
            if new_state == ConnectionState.CONNECTED:
                self._start_health_check()

            # Stop monitoring when disconnected
            elif (
                old_state == ConnectionState.CONNECTED
                and new_state != ConnectionState.CONNECTED
            ):
                self._stop_monitoring_tasks()

        except Exception as e:
            logger.error("Error in state change callback: %s", e)

    def _stop_monitoring_tasks(self):
        """Stop all monitoring tasks"""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            self._health_check_task = None
        if self._client_monitor_task and not self._client_monitor_task.done():
            self._client_monitor_task.cancel()
            self._client_monitor_task = None

    async def send_request(self, request: MCPSdkRequest) -> MCPSdkResponse:
        """
        Send request through FastMCP client

        Args:
            request: SDK request

        Returns:
            SDK response

        Raises:
            MCPClientError: MCP client error
        """
        # Check for client errors first
        if self._client_error:
            logger.warning(
                "Client error detected: %s, triggering reconnect", self._client_error
            )
            self._connection_manager.trigger_reconnect(
                f"Client error: {self._client_error}"
            )
            self._client_error = None

        # Quick connection check and trigger reconnect if needed
        if not self._connection_manager.is_connected or not self._client:
            if not self._connection_manager.is_connecting:
                logger.info("Connection lost, triggering reconnect")
                self._connection_manager.trigger_reconnect("Request needs connection")

            # Wait briefly for connection
            max_wait = 30.0  # Reduced from 45s
            waited = 0.0

            while waited < max_wait:
                if self._connection_manager.is_connected and self._client:
                    break

                if self._connection_manager.state == ConnectionState.FAILED:
                    raise MCPClientError("Connection failed permanently")

                await asyncio.sleep(1.0)
                waited += 1.0

                if waited % 10 == 0:  # Log every 10 seconds
                    logger.debug("Waiting for connection... (%.0fs)", waited)

            if not self._connection_manager.is_connected or not self._client:
                raise MCPClientError(f"Connection timeout after {max_wait}s")

        try:
            # Parse request
            if isinstance(request.request, str):
                mcp_request = json.loads(request.request)
            else:
                mcp_request = request.request

            method = mcp_request.get("method")
            params = mcp_request.get("params", {})

            # Forward to MCP server
            response_string = await self._forward_mcp_request(method, params)

            # Update success metrics
            self._last_successful_request = time.time()
            if self._connection_errors > 0:
                self._connection_errors = 0

            # Build response
            return MCPSdkResponse(
                request_id=request.request_id,
                endpoint=request.endpoint,
                version=request.version,
                method=request.method,
                ts=str(int(time.time() * 1000)),
                response=response_string,
                sign=None,
            )

        except Exception as e:
            if self._is_unauthorized(e):
                logger.warning(
                    "HTTP 401 Unauthorized during request, triggering reconnect"
                )
                self._connection_manager.trigger_reconnect("HTTP 401 Unauthorized")
                error_string = json.dumps(
                    {"error": "HTTP 401 Unauthorized"},
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

            error_str = str(e).lower()
            # Check for connection-related errors
            is_connection_error = any(
                err in error_str
                for err in [
                    "remote",
                    "protocol",
                    "connection",
                    "closed",
                    "timeout",
                    "eof",
                    "reset",
                ]
            )

            if is_connection_error:
                logger.warning(
                    "Connection error in request: %s, triggering reconnect", e
                )
                self._connection_manager.trigger_reconnect(
                    f"Request connection error: {e}"
                )
            else:
                logger.error("Request failed: %s", e)
                self._connection_errors += 1
                if self._connection_errors >= 3:
                    logger.warning("Multiple errors detected, triggering reconnect")
                    self._connection_manager.trigger_reconnect(
                        "Multiple request errors"
                    )

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

    async def _forward_mcp_request(self, method: str, params: dict[str, Any]) -> str:
        """
        Forward MCP request to server using FastMCP

        Args:
            method: MCP method name
            params: MCP method parameters

        Returns:
            MCP response data as JSON string
        """
        if not self._client:
            raise MCPClientError("MCP client not available")

        try:
            # Route to appropriate FastMCP method based on MCP method type
            if method == "tools/list":
                # Add timeout protection for API calls
                tools = await asyncio.wait_for(
                    self._client.list_tools(),
                    # Use shorter timeout for individual requests
                    timeout=min(30, self.timeout),
                )
                # Convert tool object to dictionary structure conforming to MCP protocol
                logger.info("Tools: %s", tools)
                tools_list = []
                for tool in tools:
                    tool_any = cast(Any, tool)
                    tool_dict = {
                        "name": tool_any.name,
                        "description": tool_any.description,
                    }
                    # Add title field (if available, otherwise use name)
                    if getattr(tool_any, "title", None):
                        tool_dict["title"] = tool_any.title
                    else:
                        tool_dict["title"] = tool_any.name

                    # Add inputSchema field
                    if getattr(tool_any, "inputSchema", None):
                        tool_dict["inputSchema"] = tool_any.inputSchema
                    elif getattr(tool_any, "parameters", None):
                        tool_dict["inputSchema"] = tool_any.parameters
                    else:
                        # Provide default inputSchema
                        tool_dict["inputSchema"] = {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        }

                    tools_list.append(tool_dict)

                # Build MCP protocol compliant response structure
                response_data: dict[str, Any] = {"tools": tools_list}

                # Add nextCursor field (if pagination is needed)
                # Can be set based on actual pagination logic
                if params.get("cursor") or len(tools_list) > 0:
                    # If pagination is needed, can set nextCursor here
                    # response_data["nextCursor"] = "next-page-cursor"
                    pass

                # Return tools list response
                return json.dumps(
                    response_data, separators=(",", ":"), ensure_ascii=False
                )

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if not tool_name:
                    raise MCPClientError("Tool call missing name parameter")

                # Add timeout protection for tool calls
                result = await asyncio.wait_for(
                    self._client.call_tool(tool_name, arguments),
                    # Use reasonable timeout for tool calls
                    timeout=min(120, self.timeout),
                )

                # Build MCP protocol compliant tools/call response structure
                call_response_data: dict[str, Any] = {"content": [], "isError": False}

                # Handle FastMCP returned results
                result_any = cast(Any, result)
                if getattr(result_any, "content", None):
                    # result.content is an array, iterate through each content item
                    for content_item in result_any.content:
                        content_any = cast(Any, content_item)
                        if (
                            getattr(content_any, "text", None) is not None
                            and getattr(content_any, "type", None) is not None
                        ):
                            # Standard content object, add directly
                            call_response_data["content"].append(
                                {"type": content_any.type, "text": content_any.text}
                            )
                        elif getattr(content_any, "text", None) is not None:
                            # Only text attribute, default type is text
                            call_response_data["content"].append(
                                {"type": "text", "text": content_any.text}
                            )
                        else:
                            # Other types, try to convert to string
                            call_response_data["content"].append(
                                {"type": "text", "text": str(content_item)}
                            )
                else:
                    # If no content attribute or content is empty, use result directly
                    call_response_data["content"].append(
                        {"type": "text", "text": str(result)}
                    )

            else:
                raise MCPClientError(f"Unsupported MCP method: {method}")

            # Convert response data to JSON string
            return json.dumps(
                call_response_data, separators=(",", ":"), ensure_ascii=False
            )

        except Exception as e:
            if self._is_unauthorized(e):
                logger.warning(
                    "HTTP 401 Unauthorized from MCP server, triggering reconnect"
                )
                self._connection_manager.trigger_reconnect("HTTP 401 Unauthorized")
                return json.dumps(
                    {"error": "HTTP 401 Unauthorized"},
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            # Connection errors are now handled by the httpx client layer
            logger.error("Error forwarding MCP request: %s", e)
            error_response = {"error": str(e)}
            return json.dumps(error_response, separators=(",", ":"), ensure_ascii=False)

    async def disconnect(self):
        """Disconnect from MCP server"""
        logger.info("Disconnecting MCP client...")

        # Remove log handler
        self._remove_sse_log_handler()

        # Stop monitoring tasks
        self._stop_monitoring_tasks()

        # Disconnect from connection manager
        await self._connection_manager.disconnect()

        # Clean up client
        await self._cleanup_client()

        logger.info("MCP client disconnected")

    def _install_sse_log_handler(self):
        """Install log handler to capture SSE errors"""
        try:
            sse_logger = logging.getLogger("mcp.client.sse")
            self._log_handler = SSEErrorLogHandler(self)
            sse_logger.addHandler(self._log_handler)
            logger.debug("SSE error log handler installed")
        except Exception as e:
            logger.warning("Failed to install SSE log handler: %s", e)

    def _remove_sse_log_handler(self):
        """Remove SSE error log handler"""
        try:
            if self._log_handler:
                sse_logger = logging.getLogger("mcp.client.sse")
                sse_logger.removeHandler(self._log_handler)
                self._log_handler = None
                logger.debug("SSE error log handler removed")
        except Exception as e:
            logger.warning("Failed to remove SSE log handler: %s", e)

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connection_manager.is_connected and self._client is not None

    def _start_health_check(self):
        """Start health check task for connections"""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.debug("Health check started")

    async def _health_check_loop(self):
        """Health check loop to monitor connection"""
        try:
            check_interval = 60  # Check every minute
            idle_threshold = 600  # 10 minutes idle triggers reconnect

            while self._connected:
                await asyncio.sleep(check_interval)

                if not self._connected:
                    break

                # Check for client errors
                if self._client_error:
                    logger.warning(
                        "Client error detected in health check: %s", self._client_error
                    )
                    self._connection_manager.trigger_reconnect(
                        f"Client error: {self._client_error}"
                    )
                    break

                # Check idle time
                idle_time = time.time() - self._last_successful_request

                if idle_time > idle_threshold:
                    logger.warning(
                        "Connection idle for %.1fs, triggering reconnect", idle_time
                    )
                    self._connection_manager.trigger_reconnect("Long idle period")
                    break

                # Periodic connection test for HTTP/SSE (if idle > 2 minutes)
                if idle_time > 120 and self.mcp_server_endpoint.startswith(
                    ("http://", "https://")
                ):
                    try:
                        logger.debug("Health check: testing idle connection")
                        # Quick health check with short timeout
                        if not self._client:
                            raise MCPClientError("MCP client not available")
                        await asyncio.wait_for(self._client.list_tools(), timeout=8)
                        self._last_successful_request = time.time()
                        self._connection_errors = 0
                        logger.debug("Health check: idle connection test passed")
                    except Exception as e:
                        logger.warning(
                            "Health check: idle connection test failed: %s", e
                        )
                        self._connection_manager.trigger_reconnect(
                            f"Health check failed: {e}"
                        )
                        break

        except asyncio.CancelledError:
            logger.debug("Health check cancelled")
        except Exception as e:
            logger.error("Error in health check loop: %s", e)

    def _start_client_monitor(self):
        """Start client monitor to detect background errors"""
        if self._client_monitor_task is None or self._client_monitor_task.done():
            self._client_monitor_task = asyncio.create_task(self._client_monitor_loop())
            logger.debug("Client monitor started")

    async def _client_monitor_loop(self):
        """Monitor client by making actual API calls to detect SSE errors"""
        try:
            check_interval = 45  # Check every 45 seconds
            consecutive_failures = 0
            max_failures = 2  # 2 consecutive failures trigger reconnect

            while self._connected and self._client:
                await asyncio.sleep(check_interval)

                if not self._connected or not self._client:
                    break

                # Make an actual API call to verify SSE connection is alive
                try:
                    logger.debug("Client monitor: performing health check")
                    await asyncio.wait_for(self._client.list_tools(), timeout=10.0)
                    # Success - reset failure counter
                    consecutive_failures = 0
                    self._connection_errors = 0
                    logger.debug("Client monitor: health check passed")

                except asyncio.TimeoutError:
                    consecutive_failures += 1
                    logger.warning(
                        "Client monitor: health check timeout (%d/%d)",
                        consecutive_failures,
                        max_failures,
                    )
                    if consecutive_failures >= max_failures:
                        logger.warning("Client unresponsive, triggering reconnect")
                        self._connection_manager.trigger_reconnect(
                            "Client health check timeout"
                        )
                        break

                except Exception as e:
                    consecutive_failures += 1
                    error_str = str(e).lower()
                    logger.warning(
                        "Client monitor: health check failed (%d/%d): %s",
                        consecutive_failures,
                        max_failures,
                        e,
                    )

                    # Check if it's a connection error
                    is_connection_error = any(
                        err in error_str
                        for err in [
                            "remote",
                            "protocol",
                            "connection",
                            "closed",
                            "eof",
                            "reset",
                            "broken",
                            "pipe",
                            "timeout",
                        ]
                    )

                    if is_connection_error or consecutive_failures >= max_failures:
                        logger.warning(
                            "Connection error detected, triggering reconnect"
                        )
                        self._connection_manager.trigger_reconnect(
                            f"Client health check failed: {e}"
                        )
                        break

        except asyncio.CancelledError:
            logger.debug("Client monitor cancelled")
        except Exception as e:
            logger.error("Error in client monitor loop: %s", e)

    def _check_network_connectivity_sync(self) -> bool:
        """Network connectivity check for connection manager"""
        # Always return True to allow connection attempts
        # Actual connectivity will be verified during connection
        return True

    def _create_transport(self):
        """
        Create transport for MCP server
        """

        # Debug Custom Header
        logger.info("Custom MCP Client Header: %s", self._resolved_headers)

        # Determine transport type based on URL
        if self.mcp_server_endpoint.endswith("/sse"):
            logger.info("Using SSE transport")
            transport = SSETransport(
                url=self.mcp_server_endpoint,
                sse_read_timeout=self.timeout,  # SSE-specific read timeout
                headers=self._resolved_headers,
                httpx_client_factory=self._create_custom_httpx_client,
            )
        else:
            logger.info("Using StreamableHttp transport")
            transport = StreamableHttpTransport(
                url=self.mcp_server_endpoint,
                headers=self._resolved_headers,
                httpx_client_factory=self._create_custom_httpx_client,
            )
        return transport

    def _create_custom_httpx_client(
        self,
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
        follow_redirects: bool | None = None,
        **_kwargs: object,
    ) -> httpx.AsyncClient:
        """
        Create custom httpx client factory with extended timeout and error monitoring
        Custom httpx client factory that accepts FastMCP transport parameters
        FastMCP may pass headers, auth, and other parameters
        """

        timeout_config = httpx.Timeout(
            connect=30.0,  # Connection timeout
            read=self.timeout,  # Read timeout for SSE streams
            write=30.0,  # Write timeout
            pool=30.0,  # Pool timeout
        )

        if timeout is not None:
            timeout_config = timeout

        # Create event hooks to monitor requests and responses
        async def response_hook(response: httpx.Response) -> None:
            if response.status_code == 401:
                logger.warning(
                    "MCP server unauthorized (HTTP 401): %s",
                    response.url,
                )
                self._connection_errors += 1
                self._connection_manager.trigger_reconnect("HTTP 401 Unauthorized")
            elif response.status_code >= 400:
                logger.warning(
                    "MCP server HTTP error: %d %s",
                    response.status_code,
                    response.url,
                )

        limits = httpx.Limits(
            max_keepalive_connections=10,
            max_connections=20,
            keepalive_expiry=300,
        )

        return httpx.AsyncClient(
            timeout=timeout_config,
            limits=limits,
            event_hooks={"response": [response_hook]},
            headers=headers,
            auth=auth,
            follow_redirects=follow_redirects
            if follow_redirects is not None
            else False,
        )
