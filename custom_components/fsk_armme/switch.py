"""Zone bypass switches for ArmME."""

from __future__ import annotations

from typing import Any, cast

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ArmmeApi, ArmmeSystemState
from .const import DOMAIN
from .coordinator import ArmmeDataUpdateCoordinator
from .entity import ArmmeEntity


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


class ArmmeZoneBypassSwitch(ArmmeEntity, SwitchEntity):
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
        super().__init__(
            coordinator,
            api,
            unique_id_suffix=f"zone-{zone_number}-bypass",
            name=f"{friendly_name} bypass",
        )
        self._zone_number = zone_number
        self._attr_translation_key = "zone_bypass"

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
        await self.api.async_set_zone_bypass(
            zone=self._zone_number,
            partition=self.coordinator.partition,
            bypass=True,
            panel_code=self.api.panel_code,
            session_id=self.coordinator.last_session_id,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Remove bypass from the zone."""
        await self.api.async_set_zone_bypass(
            zone=self._zone_number,
            partition=self.coordinator.partition,
            bypass=False,
            panel_code=self.api.panel_code,
            session_id=self.coordinator.last_session_id,
        )
        await self.coordinator.async_request_refresh()
