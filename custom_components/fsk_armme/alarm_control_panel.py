"""Alarm control panel platform for ArmME."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ArmmeApi, ArmmeOperationError
from .const import DOMAIN
from .coordinator import ArmmeDataUpdateCoordinator
from .pyfskelec.exceptions import ArmMEAuthError, ArmMERequestError
from .pyfskelec.models import PartitionStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ArmME alarm control panel entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ArmmeDataUpdateCoordinator = data["coordinator"]
    api: ArmmeApi = data["api"]

    partition_names = api.properties.names.partition_names or {}
    if coordinator.data and coordinator.data.partitions:
        partition_numbers = list(range(1, len(coordinator.data.partitions) + 1))
    else:
        partition_numbers = sorted(
            {
                int(key)
                for key in partition_names
                if isinstance(key, str) and key.isdigit()
            }
        )
        if not partition_numbers:
            partition_numbers = [coordinator.partition]

    entities: list[ArmmeAlarmControlPanel] = []
    for number in partition_numbers:
        name = partition_names.get(str(number), f"Partition {number}")
        entities.append(
            ArmmeAlarmControlPanel(
                coordinator=coordinator,
                api=api,
                partition=number,
                friendly_name=name,
            )
        )

    async_add_entities(entities)


class ArmmeAlarmControlPanel(
    CoordinatorEntity[ArmmeDataUpdateCoordinator],
    AlarmControlPanelEntity,
):
    """Representation of an ArmME partition."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
    )
    _attr_code_format = CodeFormat.NUMBER
    _attr_code_arm_required = False

    def __init__(
        self,
        *,
        coordinator: ArmmeDataUpdateCoordinator,
        api: ArmmeApi,
        partition: int,
        friendly_name: str,
    ) -> None:
        """Initialise the alarm control panel entity."""
        super().__init__(coordinator)
        self._api = api
        self._partition = partition
        device = api.device
        props = api.properties
        serial = device.serial_no or str(device.device_id)
        self._attr_name = friendly_name
        self._attr_unique_id = f"{serial}-partition-{partition}"
        sw_version = getattr(props, "version_panel", None) or getattr(
            props, "version_com", None
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="ArmME",
            name=device.name,
            model=device.device_type_name,
            sw_version=sw_version,
        )

    @property
    def available(self) -> bool:
        """Return entity availability based on coordinator status."""
        return self.coordinator.last_update_success and super().available

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the current alarm state."""
        status = self._partition_status()
        if status is None:
            return None
        if status.alarmed:
            return AlarmControlPanelState.TRIGGERED
        if status.away_armed:
            return AlarmControlPanelState.ARMED_AWAY
        if status.stay_armed1:
            return AlarmControlPanelState.ARMED_HOME
        return AlarmControlPanelState.DISARMED

    def _partition_status(self) -> PartitionStatus | None:
        """Return cached partition status."""
        data = self.coordinator.data
        if not data.partitions:
            return None
        index = self._partition - 1
        if index < 0 or index >= len(data.partitions):
            return None
        return data.partitions[index]

    def _resolve_code(self, code: str | None) -> str:
        """Return a valid panel code from user input or stored fallback."""
        if code:
            return code
        fallback = self._api.panel_code
        if fallback:
            return fallback
        raise HomeAssistantError("A panel code is required for this operation.")

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Arm stay/home."""
        await self._async_execute(
            self._api.async_arm_stay,
            partition=self._partition,
            panel_code=self._resolve_code(code),
        )

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Arm away."""
        await self._async_execute(
            self._api.async_arm_away,
            partition=self._partition,
            panel_code=self._resolve_code(code),
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Disarm the partition."""
        await self._async_execute(
            self._api.async_disarm,
            partition=self._partition,
            panel_code=self._resolve_code(code),
        )

    async def _async_execute(
        self,
        command: Callable[..., Awaitable[None]],
        **kwargs: Any,
    ) -> None:
        """Execute an ArmME command and refresh the coordinator."""
        try:
            await command(**kwargs)
        except ArmMEAuthError as err:
            raise HomeAssistantError("Authentication failed with ArmME API") from err
        except ArmmeOperationError as err:
            raise HomeAssistantError(err.result.message or str(err)) from err
        except ArmMERequestError as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()
