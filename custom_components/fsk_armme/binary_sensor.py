"""Binary sensors for the ArmME integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import cast

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ArmmeApi, ArmmeSystemState, ArmmeZoneState
from .const import DOMAIN
from .coordinator import ArmmeDataUpdateCoordinator
from .entity import ArmmeEntity


@dataclass(frozen=True, kw_only=True)
class ArmmeBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe an ArmME binary sensor."""

    value_extractor: Callable[[ArmmeSystemState, int], bool | None]
    unique_id_suffix: Callable[[int], str]


ZONE_SENSOR_DESCRIPTION = ArmmeBinarySensorEntityDescription(
    key="zone",
    unique_id_suffix=lambda index: f"zone-{index}",
    value_extractor=lambda state, index: (
        state.zones[index - 1].is_active
        if 0 <= index - 1 < len(state.zones)
        else None
    ),
)

PARTITION_AC_FAIL_DESCRIPTION = ArmmeBinarySensorEntityDescription(
    key="partition-ac-fail",
    translation_key="partition_ac_fail",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    unique_id_suffix=lambda index: f"partition-{index}-ac-fail",
    value_extractor=lambda state, index: (
        state.partitions[index - 1].ac_fail
        if 0 <= index - 1 < len(state.partitions)
        else None
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ArmME binary sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ArmmeDataUpdateCoordinator = data["coordinator"]
    api: ArmmeApi = data["api"]

    entities: list[BinarySensorEntity] = []
    entities.extend(_build_zone_sensors(coordinator, api))
    entities.extend(_build_partition_sensors(coordinator, api))

    async_add_entities(entities)


def _build_zone_sensors(
    coordinator: ArmmeDataUpdateCoordinator,
    api: ArmmeApi,
) -> Iterable[BinarySensorEntity]:
    zone_states = list(coordinator.data.zones) if coordinator.data else []
    if not zone_states:
        zone_states = _fallback_zones(api)
    return [
        ArmmeBinarySensor(
            coordinator=coordinator,
            api=api,
            description=ZONE_SENSOR_DESCRIPTION,
            index=zone.number,
            display_name=zone.name,
        )
        for zone in zone_states
    ]


def _fallback_zones(api: ArmmeApi) -> list[ArmmeZoneState]:
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
    return sorted(fallback_zones, key=lambda zone: zone.number)


def _build_partition_sensors(
    coordinator: ArmmeDataUpdateCoordinator,
    api: ArmmeApi,
) -> Iterable[BinarySensorEntity]:
    if not coordinator.data or not coordinator.data.partitions:
        return []

    partition_names = api.properties.names.partition_names or {}
    return [
        ArmmeBinarySensor(
            coordinator=coordinator,
            api=api,
            description=PARTITION_AC_FAIL_DESCRIPTION,
            index=index,
            display_name=(
                f"{partition_names.get(str(index), f'Partition {index}')} AC failure"
            ),
        )
        for index in range(1, len(coordinator.data.partitions) + 1)
    ]


class ArmmeBinarySensor(ArmmeEntity, BinarySensorEntity):
    """Generic ArmME binary sensor driven by entity descriptions."""

    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator: ArmmeDataUpdateCoordinator,
        api: ArmmeApi,
        description: ArmmeBinarySensorEntityDescription,
        index: int,
        display_name: str | None,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(
            coordinator,
            api,
            unique_id_suffix=description.unique_id_suffix(index),
            name=display_name,
            translation_key=description.translation_key,
        )
        self.entity_description: ArmmeBinarySensorEntityDescription = description
        self._index = index
        if display_name is None and description.translation_key is None:
            # Default placeholder when no translation or explicit name provided.
            self._attr_name = description.key
    @property
    def is_on(self) -> bool | None:
        """Return the binary sensor value."""
        data = cast(ArmmeSystemState | None, getattr(self.coordinator, "data", None))
        if data is None:
            return None
        return self.entity_description.value_extractor(data, self._index)
