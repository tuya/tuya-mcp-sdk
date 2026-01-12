"""
Connection Manager - Unified management of network connection state and reconnection strategies
"""

import asyncio
import logging
import random
import time
from typing import Optional, Callable, Any, List
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state enumeration"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    SHUTDOWN = "shutdown"


@dataclass
class ReconnectConfig:
    """Reconnection configuration"""
    base_interval: float = 1.0  # Base reconnection interval (seconds)
    max_interval: float = 120.0  # Maximum reconnection interval (seconds)
    max_retries: int = -1  # Maximum retry count, -1 means unlimited retries
    backoff_multiplier: float = 2.0  # Backoff multiplier
    jitter_range: float = 0.1  # Jitter range (0-1)
    reset_threshold: int = 100  # Retry count threshold for resetting reconnection interval


@dataclass
class NetworkInfo:
    """Network information"""
    is_available: bool = True
    last_check_time: float = 0
    check_interval: float = 5.0  # Network check interval (seconds)


class ConnectionManager:
    """
    Connection Manager

    Provides unified connection state management, reconnection strategies, and network monitoring capabilities
    """

    def __init__(self, reconnect_config: Optional[ReconnectConfig] = None):
        """
        Initialize connection manager

        Args:
            reconnect_config: Reconnection configuration, uses default if None
        """
        self.config = reconnect_config or ReconnectConfig()

        # State management
        self._state = ConnectionState.DISCONNECTED
        self._last_state_change = time.time()

        # Reconnection management
        self._retry_count = 0
        self._current_interval = self.config.base_interval
        self._reconnect_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        # Network monitoring
        self._network_info = NetworkInfo()
        self._network_monitor_task: Optional[asyncio.Task] = None

        # Callback functions
        self._state_change_callbacks: List[Callable[[
            ConnectionState, ConnectionState], None]] = []
        self._network_change_callbacks: List[Callable[[bool], None]] = []

        # Connector function
        self._connector: Optional[Callable[[], Any]] = None
        self._network_checker: Optional[Callable[[], bool]] = None

    def set_connector(self, connector: Callable[[], Any]):
        """Set connector function"""
        self._connector = connector

    def set_network_checker(self, checker: Callable[[], bool]):
        """Set network checker function"""
        self._network_checker = checker

    def add_state_change_callback(self, callback: Callable[[ConnectionState, ConnectionState], None]):
        """Add state change callback"""
        self._state_change_callbacks.append(callback)

    def add_network_change_callback(self, callback: Callable[[bool], None]):
        """Add network state change callback"""
        self._network_change_callbacks.append(callback)

    def _set_state(self, new_state: ConnectionState):
        """Set connection state"""
        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            self._last_state_change = time.time()

            logger.info(
                "Connection state changed: %s -> %s", old_state.value, new_state.value)

            # Notify state change callbacks
            for callback in self._state_change_callbacks:
                try:
                    callback(old_state, new_state)
                except Exception as e:
                    logger.error("Error in state change callback: %s", e)

    @property
    def state(self) -> ConnectionState:
        """Get current connection state"""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._state == ConnectionState.CONNECTED

    @property
    def is_connecting(self) -> bool:
        """Check if connecting"""
        return self._state in (ConnectionState.CONNECTING, ConnectionState.RECONNECTING)

    async def start_monitoring(self):
        """Start network monitoring"""
        if self._network_monitor_task is None or self._network_monitor_task.done():
            self._network_monitor_task = asyncio.create_task(
                self._network_monitor_loop())
            logger.info("Network monitoring started")

    async def stop_monitoring(self):
        """Stop network monitoring"""
        if self._network_monitor_task and not self._network_monitor_task.done():
            self._network_monitor_task.cancel()
            try:
                await self._network_monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("Network monitoring stopped")

    async def connect(self) -> bool:
        """
        Establish connection

        Returns:
            Whether connection was successful
        """
        if self._state == ConnectionState.SHUTDOWN:
            logger.warning("Connection manager is shutdown, cannot connect")
            return False

        # Clear stop event to allow reconnection
        self._stop_event.clear()
        self._set_state(ConnectionState.CONNECTING)

        try:
            if self._connector:
                await self._connector()
                self._set_state(ConnectionState.CONNECTED)
                self._reset_retry_params()
                return True
            else:
                logger.error("No connector function set")
                self._set_state(ConnectionState.FAILED)
                return False

        except Exception as e:
            logger.error("Connection failed: %s", e)
            self._set_state(ConnectionState.DISCONNECTED)
            return False

    async def disconnect(self):
        """Disconnect"""
        self._stop_event.set()

        # Stop reconnect task
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        self._set_state(ConnectionState.DISCONNECTED)

    async def shutdown(self):
        """Shutdown connection manager"""
        self._stop_event.set()
        self._set_state(ConnectionState.SHUTDOWN)

        # Stop all tasks
        await self.stop_monitoring()
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        logger.info("Connection manager shutdown")

    def trigger_reconnect(self, reason: str = "Manual trigger"):
        """
        Trigger reconnection

        Args:
            reason: Reason for reconnection
        """
        if self._state == ConnectionState.SHUTDOWN:
            logger.warning("Cannot reconnect: connection manager is shutdown")
            return

        logger.info("Triggering reconnect: %s", reason)

        # Clear stop event to allow reconnection loop to run
        self._stop_event.clear()

        # If already reconnecting, don't start again
        if self._reconnect_task and not self._reconnect_task.done():
            logger.debug("Reconnect task already running")
            return

        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """Reconnection loop"""
        logger.info("Starting reconnect loop")
        self._set_state(ConnectionState.RECONNECTING)

        while not self._stop_event.is_set():
            try:
                # Check if max retry count exceeded
                if self.config.max_retries > 0 and self._retry_count >= self.config.max_retries:
                    logger.error(
                        "Max retries (%s) reached, giving up", self.config.max_retries)
                    self._set_state(ConnectionState.FAILED)
                    break

                # Wait for network availability
                logger.debug("Checking network availability...")
                await self._wait_for_network()
                logger.debug("Network check completed")

                if self._stop_event.is_set():
                    break

                # Calculate reconnection delay (including jitter)
                delay = self._calculate_retry_delay()
                logger.info(
                    "Reconnecting in %.1fs (attempt #%s)", delay, self._retry_count + 1)

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                    # If wait succeeds, stop signal was received
                    break
                except asyncio.TimeoutError:
                    # Timeout is normal, continue reconnecting
                    pass

                if self._stop_event.is_set():
                    break

                # Attempt reconnection
                self._retry_count += 1
                logger.info("Attempting reconnection #%s", self._retry_count)

                success = await self.connect()
                logger.info("Reconnection attempt #%s result: %s",
                            self._retry_count, success)
                if success:
                    logger.info(
                        "Reconnection successful after %s attempts", self._retry_count)
                    break
                else:
                    logger.info(
                        "Reconnection attempt #%s failed, will retry", self._retry_count)
                    # Update reconnection interval
                    self._update_retry_interval()

                    # Periodically reset reconnection interval
                    if self._retry_count % self.config.reset_threshold == 0:
                        logger.info(
                            "Resetting retry interval after %s attempts", self._retry_count)
                        self._current_interval = self.config.base_interval

            except asyncio.CancelledError:
                logger.debug("Reconnect loop cancelled")
                break
            except Exception as e:
                logger.error("Error in reconnect loop: %s", e)
                await asyncio.sleep(1)  # Avoid rapid failure loops

        logger.info("Reconnect loop ended")

    def _calculate_retry_delay(self) -> float:
        """Calculate retry delay (including jitter)"""
        # Base delay
        base_delay = min(self._current_interval, self.config.max_interval)

        # Add jitter to avoid thundering herd effect
        jitter = base_delay * self.config.jitter_range * \
            (2 * random.random() - 1)
        delay = base_delay + jitter

        return max(0.1, delay)  # Minimum delay 0.1 seconds

    def _update_retry_interval(self):
        """Update retry interval"""
        self._current_interval = min(
            self._current_interval * self.config.backoff_multiplier,
            self.config.max_interval
        )

    def _reset_retry_params(self):
        """Reset retry parameters"""
        self._retry_count = 0
        self._current_interval = self.config.base_interval

    async def _wait_for_network(self):
        """Wait for network availability"""
        while not self._stop_event.is_set() and not self._network_info.is_available:
            logger.debug("Waiting for network to become available")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=1.0)
                break  # Stop signal received
            except asyncio.TimeoutError:
                # Recheck network status
                await self._check_network()

    async def _network_monitor_loop(self):
        """Network monitoring loop"""
        logger.info("Starting network monitoring loop")

        try:
            while not self._stop_event.is_set():
                try:
                    await self._check_network()

                    # Wait for next check
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self._network_info.check_interval
                        )
                        break  # Stop signal received
                    except asyncio.TimeoutError:
                        pass  # Normal timeout, continue monitoring

                except Exception as e:
                    logger.error("Error in network monitoring: %s", e)
                    await asyncio.sleep(5)  # Brief wait on error

        except asyncio.CancelledError:
            logger.debug("Network monitoring cancelled")
        finally:
            logger.info("Network monitoring loop ended")

    async def _check_network(self):
        """Check network connectivity"""
        try:
            current_time = time.time()

            # Avoid too frequent network checks
            if current_time - self._network_info.last_check_time < 1.0:
                return

            self._network_info.last_check_time = current_time

            if self._network_checker:
                try:
                    # If it's a coroutine function
                    if asyncio.iscoroutinefunction(self._network_checker):
                        is_available = await self._network_checker()
                    else:
                        is_available = self._network_checker()
                except Exception as e:
                    logger.debug("Network check failed: %s", e)
                    is_available = False
            else:
                # Default to network available
                is_available = True

            # Check if network status changed
            if is_available != self._network_info.is_available:
                old_status = self._network_info.is_available
                self._network_info.is_available = is_available

                logger.info(
                    "Network status changed: %s -> %s", old_status, is_available)

                # Notify network state change callbacks
                for callback in self._network_change_callbacks:
                    try:
                        callback(is_available)
                    except Exception as e:
                        logger.error("Error in network change callback: %s", e)

                # Trigger immediate reconnection on network recovery
                if is_available and not old_status and self._state == ConnectionState.DISCONNECTED:
                    logger.info(
                        "Network recovered, triggering immediate reconnect")
                    self.trigger_reconnect("Network recovery")

        except Exception as e:
            logger.error("Error checking network: %s", e)
