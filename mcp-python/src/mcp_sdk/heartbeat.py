"""
Heartbeat Manager
Heartbeat Manager - Based on WebSocket ping/pong mechanism
"""

import asyncio
import logging
import time
from typing import Optional

from .exceptions import HeartbeatError

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """
    Heartbeat Manager
    Heartbeat manager based on WebSocket ping/pong mechanism

    Note: Actual heartbeat is handled automatically by WebSocket client library (ping_interval, ping_timeout)
    This manager is mainly used for monitoring connection status
    """

    def __init__(self, ping_interval: int = 30, ping_timeout: int = 10):
        """
        Initialize heartbeat manager

        Args:
            ping_interval: WebSocket ping interval (seconds)
            ping_timeout: WebSocket ping timeout (seconds)
        """
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        self._running = False
        self._monitor_task: Optional[asyncio.Task[None]] = None
        self._last_pong_time = 0
        self._websocket = None
        self._connection_failure_callback = None  # Connection failure callback

    def set_websocket(self, websocket):
        """Set WebSocket connection"""
        self._websocket = websocket
        self._last_pong_time = time.time()

    def set_connection_failure_callback(self, callback):
        """Set connection failure callback function"""
        self._connection_failure_callback = callback

    async def start(self):
        """Start heartbeat monitoring"""
        if self._running:
            return

        self._running = True
        self._last_pong_time = time.time()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(
            "Heartbeat monitor started, ping_interval: %ss, ping_timeout: %ss",
            self.ping_interval,
            self.ping_timeout,
        )

    async def stop(self):
        """Stop heartbeat monitoring"""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        logger.info("Heartbeat monitor stopped")

    async def _monitor_loop(self):
        """
        Monitor loop - Never-ending heartbeat monitoring
        Note: Actual ping/pong is handled automatically by WebSocket library
        This only monitors connection status
        """
        while self._running:
            try:
                await asyncio.sleep(self.ping_interval)

                if not self._running:
                    break

                # Check WebSocket connection status
                if self._websocket:
                    # Check if connection is closed
                    if hasattr(self._websocket, "closed") and self._websocket.closed:
                        logger.warning("WebSocket connection is closed")
                        raise HeartbeatError("WebSocket connection closed")

                    if hasattr(self._websocket, "state"):
                        try:
                            ws_state = self._websocket.state

                            expected_open = None
                            try:
                                import websockets

                                _connection_state = getattr(
                                    websockets, "ConnectionState", None
                                )
                                expected_open = (
                                    getattr(_connection_state, "OPEN", None)
                                    if _connection_state is not None
                                    else None
                                )
                            except Exception:
                                expected_open = None

                            if expected_open is None:
                                try:
                                    from websockets.protocol import State as _State

                                    expected_open = getattr(_State, "OPEN", None)
                                except Exception:
                                    expected_open = None

                            is_open = False
                            if expected_open is not None:
                                is_open = ws_state == expected_open

                            if not is_open:
                                ws_state_name = getattr(ws_state, "name", None)
                                expected_name = getattr(expected_open, "name", None)
                                if (
                                    ws_state_name is not None
                                    and expected_name is not None
                                ):
                                    is_open = ws_state_name == expected_name

                            if not is_open:
                                ws_state_str = str(ws_state).upper()
                                if (
                                    "OPEN" in ws_state_str
                                    and "CLOSE" not in ws_state_str
                                ):
                                    is_open = True

                            if expected_open is not None and not is_open:
                                logger.warning(
                                    "WebSocket state is not OPEN: %s",
                                    ws_state,
                                )
                                raise HeartbeatError(
                                    f"WebSocket state invalid: {ws_state}"
                                )
                        except Exception:
                            pass

                    # Actively send ping to test connection (if websocket supports it)
                    try:
                        if hasattr(self._websocket, "ping"):
                            logger.debug("Sending heartbeat ping...")
                            pong_waiter = await self._websocket.ping()
                            # Wait for pong response, set timeout
                            await asyncio.wait_for(
                                pong_waiter, timeout=self.ping_timeout
                            )
                            logger.debug("Heartbeat pong received")
                            self._last_pong_time = time.time()
                        else:
                            # If no ping method, at least update timestamp
                            self._last_pong_time = time.time()
                    except asyncio.TimeoutError:
                        err_msg = f"Heartbeat ping timeout after {self.ping_timeout}s"
                        logger.warning(err_msg)
                        raise HeartbeatError(err_msg) from None
                    except Exception as ping_error:
                        err_msg = f"Heartbeat ping failed: {ping_error}"
                        logger.warning(err_msg)
                        raise HeartbeatError(err_msg) from None

                    # Check if timeout (based on ping_interval + ping_timeout)
                    current_time = time.time()
                    expected_timeout = self.ping_interval + self.ping_timeout
                    if current_time - self._last_pong_time > expected_timeout * 3:
                        err_msg = f"No pong received for {current_time - self._last_pong_time}s"
                        logger.warning(err_msg)
                        raise HeartbeatError(err_msg) from None
                else:
                    err_msg = "No WebSocket connection for heartbeat monitoring"
                    logger.debug(err_msg)
                    # If no WebSocket connection, wait a while and continue checking
                    await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                err_msg = f"Heartbeat monitoring error: {e}"
                logger.error(err_msg, exc_info=True)
                if self._running:
                    # Notify connection failure but don't exit monitoring loop
                    if self._connection_failure_callback:
                        try:
                            await self._connection_failure_callback(e)
                        except Exception as callback_error:
                            err_msg = f"Error in connection failure callback: {callback_error}"
                            logger.error(err_msg, exc_info=True)

                    # Wait briefly and continue monitoring
                    await asyncio.sleep(5)

    def on_websocket_message(self):
        """Called when WebSocket message is received (indicating connection is normal)"""
        self._last_pong_time = time.time()

    def mark_service_offline(self):
        """Mark service as offline"""
        logger.warning("Service marked as offline")
        self._running = False
        # Can add more offline state handling logic here
        # For example: notify other components, record status, etc.

    @property
    def is_running(self) -> bool:
        """Check if heartbeat monitoring is running"""
        return self._running

    @property
    def ping_config(self) -> dict[str, int]:
        """Get ping configuration for WebSocket connection"""
        return {"ping_interval": self.ping_interval, "ping_timeout": self.ping_timeout}
