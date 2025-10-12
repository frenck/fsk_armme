"""Zone-level binary sensors for ArmME."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ArmmeApi, ArmmeZoneState
from .const import DOMAIN
from .coordinator import ArmmeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ArmME zone sensors based on a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ArmmeDataUpdateCoordinator = data["coordinator"]
    api: ArmmeApi = data["api"]

    zone_states = list(coordinator.data.zones) if coordinator.data else []
    if not zone_states:
        zone_names = api.properties.names.zone_names or {}
        fallback_zones: list[ArmmeZoneState] = []
        for key, value in zone_names.items():
            try:
                index = int(key)
            except (TypeError, ValueError):
                continue
            fallback_zones.append(
                ArmmeZoneState(
                    number=index,
                    name=value or f"Zone {index}",
                    is_active=False,
                    bypassed=False,
                )
            )
        zone_states = sorted(fallback_zones, key=lambda zone: zone.number)

    entities = [
        ArmmeZoneBinarySensor(
            coordinator=coordinator,
            api=api,
            zone_number=zone.number,
            friendly_name=zone.name,
        )
        for zone in zone_states
    ]
    async_add_entities(entities)


class ArmmeZoneBinarySensor(
    CoordinatorEntity[ArmmeDataUpdateCoordinator],
    BinarySensorEntity,
):
    """Binary sensor tracking a single ArmME zone."""

    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator: ArmmeDataUpdateCoordinator,
        api: ArmmeApi,
        zone_number: int,
        friendly_name: str,
    ) -> None:
        """Initialise the zone binary sensor."""
        super().__init__(coordinator)
        self._api = api
        self._zone_number = zone_number
        device = api.device
        props = api.properties

        self._attr_name = friendly_name or f"Zone {zone_number}"
        serial = device.serial_no or str(device.device_id)
        self._attr_unique_id = f"{serial}-zone-{zone_number}"
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
        """Entity availability based on coordinator refresh."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        """Return True when the zone is triggered."""
        state = self._zone_state
        if state is None:
            return None
        return state.is_active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra diagnostic attributes."""
        state = self._zone_state
        attrs: dict[str, Any] = {"zone_number": self._zone_number}
        if state:
            attrs["bypassed"] = state.bypassed
        return attrs

    @property
    def _zone_state(self) -> ArmmeZoneState | None:
        """Return the latest zone status from the coordinator."""
        for zone in self.coordinator.data.zones:
            if zone.number == self._zone_number:
                return zone
        return None
