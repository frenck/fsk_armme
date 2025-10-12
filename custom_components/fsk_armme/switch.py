"""Zone bypass switches for ArmME."""

from __future__ import annotations

from typing import Any, cast

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ArmmeApi, ArmmeSystemState
from .const import DOMAIN
from .coordinator import ArmmeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ArmME zone bypass switches for a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ArmmeDataUpdateCoordinator = data["coordinator"]
    api: ArmmeApi = data["api"]

    entities: list[ArmmeZoneBypassSwitch] = []
    if coordinator.data:
        entities.extend(
            ArmmeZoneBypassSwitch(
                coordinator=coordinator,
                api=api,
                zone_number=zone.number,
                friendly_name=zone.name,
            )
            for zone in coordinator.data.zones
        )
    async_add_entities(entities)


class ArmmeZoneBypassSwitch(
    CoordinatorEntity[ArmmeDataUpdateCoordinator],
    SwitchEntity,
):
    """Switch allowing ArmME zones to be bypassed or restored."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        *,
        coordinator: ArmmeDataUpdateCoordinator,
        api: ArmmeApi,
        zone_number: int,
        friendly_name: str,
    ) -> None:
        """Initialise the zone bypass switch."""
        super().__init__(coordinator)
        self._api = api
        self._zone_number = zone_number
        serial = api.device.serial_no or str(api.device.device_id)
        self._attr_unique_id = f"{serial}-zone-{zone_number}-bypass"
        self._attr_translation_key = "zone_bypass"
        self._friendly_zone_name = friendly_name

        props = api.properties
        sw_version = getattr(props, "version_panel", None) or getattr(
            props, "version_com", None
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="ArmME",
            name=api.device.name,
            model=api.device.device_type_name,
            sw_version=sw_version,
        )

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        return f"{self._friendly_zone_name} bypass"

    @property
    def available(self) -> bool:
        """Return availability based on coordinator status."""
        return self.coordinator.last_update_success and super().available

    @property
    def is_on(self) -> bool | None:
        """Return True if the zone is currently bypassed."""
        state = self._zone_state
        if state is None:
            return None
        return state[2]

    @property
    def _zone_state(self) -> tuple[str, bool, bool] | None:
        """Return the latest zone info as (name, active, bypassed)."""
        data = cast(ArmmeSystemState | None, getattr(self.coordinator, "data", None))
        if data is None:
            return None
        for zone in data.zones:
            if zone.number == self._zone_number:
                return (zone.name, zone.is_active, zone.bypassed)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Bypass the zone."""
        await self._api.async_set_zone_bypass(
            zone=self._zone_number,
            partition=self.coordinator.partition,
            bypass=True,
            panel_code=self._api.panel_code,
            session_id=self.coordinator.last_session_id,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Remove bypass from the zone."""
        await self._api.async_set_zone_bypass(
            zone=self._zone_number,
            partition=self.coordinator.partition,
            bypass=False,
            panel_code=self._api.panel_code,
            session_id=self.coordinator.last_session_id,
        )
        await self.coordinator.async_request_refresh()
