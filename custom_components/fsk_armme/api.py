"""Async wrapper around the PyFskElec ArmME client."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.core import HomeAssistant

from .pyfskelec.client import (
    ArmMEAuthError,
    ArmMEClient,
    ArmMERequestError,
    DeviceSummary,
)
from .pyfskelec.models import (
    ApiFailure,
    ComStatus,
    DeviceProperties,
    OperationResult,
    PartitionStatus,
)

_LOGGER = logging.getLogger(__name__)


class ArmmeApiError(ArmMERequestError):
    """Raised when the integration cannot recover from an API failure."""


class ArmmeOperationError(ArmMERequestError):
    """Raised when an ArmME command fails despite a valid HTTP response."""

    def __init__(self, message: str, result: OperationResult) -> None:
        """Store the full operation result for downstream consumers."""
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class ArmmeZoneState:
    """Represents a single zone's runtime status."""

    number: int
    name: str
    is_active: bool
    bypassed: bool


@dataclass(frozen=True)
class ArmmeSystemState:
    """Coordinator payload returned by the API wrapper."""

    partitions: list[PartitionStatus]
    zones: list[ArmmeZoneState]
    com_status: ComStatus | None


class ArmmeApi:
    """Thread-safe wrapper around the synchronous PyFskElec client."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        username: str,
        password: str,
        panel_code: str,
        device_id: int,
    ) -> None:
        """Initialise the API facade."""
        self._hass = hass
        self._username = username
        self._password = password
        self._panel_code = panel_code
        self._device_id = int(device_id)
        self._client = ArmMEClient()
        self._device: DeviceSummary | None = None
        self._properties: DeviceProperties | None = None
        self._lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Login and cache static device metadata."""
        async with self._lock:
            await self._hass.async_add_executor_job(self._initialize_sync)

    def _initialize_sync(self) -> None:
        """Blocking portion of the initial setup."""
        _LOGGER.debug("Authenticating with ArmME API as %s", self._username)
        self._client.login_password(self._username, self._password)
        device = self._client.get_device_by_id(self._device_id)
        if device is None:
            raise ArmMERequestError(f"Device id {self._device_id} not found for account")
        self._device = device
        self._properties = self._client.get_device_properties(device.device_id)

    @property
    def device(self) -> DeviceSummary:
        """Return the cached device summary."""
        if self._device is None:
            raise ArmmeApiError("Device metadata not initialised")
        return self._device

    @property
    def properties(self) -> DeviceProperties:
        """Return the cached device properties."""
        if self._properties is None:
            raise ArmmeApiError("Device properties not initialised")
        return self._properties

    @property
    def panel_code(self) -> str:
        """Return the stored fallback panel code."""
        return self._panel_code

    async def async_fetch_state(self, *, partition: int) -> ArmmeSystemState:
        """Fetch the latest system snapshot for the configured partition."""
        async with self._lock:
            return await self._hass.async_add_executor_job(
                self._fetch_state_sync, int(partition)
            )

    def _fetch_state_sync(self, partition: int) -> ArmmeSystemState:
        """Blocking helper that mirrors the mobile application's polling flow."""
        device = self.device
        last_error: Exception | None = None
        zone_names = self.properties.names.zone_names

        for attempt in range(2):
            _LOGGER.debug(
                "Polling ArmME device %s (attempt %s)", device.device_id, attempt + 1
            )
            session_id, _open_info = self._client.start_session(
                device,
                self._panel_code,
            )
            try:
                partitions = self._client.partition_status_all(
                    device.device_type_id,
                    device.device_id,
                    self._panel_code,
                    session_id=session_id,
                )
                if isinstance(partitions, ApiFailure):
                    last_error = ArmmeApiError(
                        partitions.message or "Partition status failure"
                    )
                    continue

                zones = self._client.zone_status(
                    device.device_type_id,
                    device.device_id,
                    self._panel_code,
                    partition,
                    session_id=session_id,
                )
                if isinstance(zones, ApiFailure):
                    last_error = ArmmeApiError(
                        zones.message or f"Zone status failure (partition {partition})"
                    )
                    continue

                com_status: ComStatus | None = None
                try:
                    com_status = self._client.get_com_status(
                        device.device_type_id,
                        device.device_id,
                        self._panel_code,
                        session_id=session_id,
                    )
                except ArmMERequestError as err:
                    _LOGGER.debug("Com status fetch failed: %s", err)

                zone_state = [
                    ArmmeZoneState(
                        number=index,
                        name=zone_names.get(str(index), f"Zone {index}"),
                        is_active=status.is_active,
                        bypassed=status.bypassed,
                    )
                    for index, status in enumerate(zones, start=1)
                ]
                return ArmmeSystemState(
                    partitions=partitions,
                    zones=zone_state,
                    com_status=com_status,
                )
            except ArmMEAuthError:
                raise
            except ArmMERequestError as err:
                last_error = err
            finally:
                try:
                    self._client.close_connection(device.device_id)
                except ArmMERequestError:
                    _LOGGER.debug("Failed to close ArmME session", exc_info=True)

        if last_error is None:
            raise ArmmeApiError("Unknown error fetching ArmME state")
        raise last_error

    async def async_arm_stay(self, *, partition: int, panel_code: str) -> None:
        """Arm the system in stay mode."""
        await self._async_run_command(
            lambda session_id: self._client.stay_arm(
                self.device.device_type_id,
                self.device.device_id,
                panel_code,
                partition=partition,
                session_id=session_id,
            ),
            panel_code=panel_code,
        )

    async def async_arm_away(self, *, partition: int, panel_code: str) -> None:
        """Arm the system in away mode."""
        await self._async_run_command(
            lambda session_id: self._client.away_arm(
                self.device.device_type_id,
                self.device.device_id,
                panel_code,
                partition=partition,
                session_id=session_id,
            ),
            panel_code=panel_code,
        )

    async def async_disarm(self, *, partition: int, panel_code: str) -> None:
        """Disarm the system."""
        await self._async_run_command(
            lambda session_id: self._client.disarm(
                self.device.device_type_id,
                self.device.device_id,
                panel_code,
                partition=partition,
                session_id=session_id,
            ),
            panel_code=panel_code,
        )

    async def _async_run_command(
        self,
        executor: Callable[[str], OperationResult],
        *,
        panel_code: str,
    ) -> None:
        """Execute a command after opening a session, retrying once on failure."""
        async with self._lock:
            await self._hass.async_add_executor_job(
                self._run_command_sync, executor, panel_code
            )

    def _run_command_sync(
        self,
        executor: Callable[[str], OperationResult],
        panel_code: str,
    ) -> None:
        """Blocking helper used by command coroutines."""
        device = self.device
        last_error: Exception | None = None

        for _attempt in range(2):
            session_id, _ = self._client.start_session(device, panel_code)
            try:
                result = executor(session_id)
            except ArmMEAuthError:
                raise
            except ArmMERequestError as err:
                last_error = err
            else:
                if not result.succeeded:
                    raise ArmmeOperationError(
                        result.message or "Operation rejected by panel", result
                    )
                return
            finally:
                try:
                    self._client.close_connection(device.device_id)
                except ArmMERequestError:
                    _LOGGER.debug(
                        "Failed to close ArmME session after command", exc_info=True
                    )

        if last_error is None:
            raise ArmmeApiError("Unknown error executing ArmME command")
        raise last_error

    async def async_shutdown(self) -> None:
        """Release any underlying HTTP resources."""
        async with self._lock:
            await self._hass.async_add_executor_job(self._client.s.close)
