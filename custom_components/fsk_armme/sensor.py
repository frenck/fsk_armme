"""Diagnostic sensors for the ArmME integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfElectricPotential
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
    """Set up ArmME sensors for a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: ArmmeDataUpdateCoordinator = data["coordinator"]
    api: ArmmeApi = data["api"]

    entities: list[SensorEntity] = [
        ArmmeSensor(coordinator=coordinator, api=api, description=description)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


def _build_device_info(api: ArmmeApi) -> DeviceInfo:
    """Return DeviceInfo shared by all ArmME entities."""
    device = api.device
    props = api.properties
    serial = device.serial_no or str(device.device_id)
    sw_version = getattr(props, "version_panel", None) or getattr(
        props, "version_com", None
    )

    return DeviceInfo(
        identifiers={(DOMAIN, serial)},
        manufacturer="ArmME",
        name=device.name,
        model=device.device_type_name,
        sw_version=sw_version,
    )


@dataclass(frozen=True, kw_only=True)
class ArmmeSensorEntityDescription(SensorEntityDescription):
    """Describe ArmME sensor metadata and extraction logic."""

    value_extractor: Callable[[ArmmeSystemState], Any | None]
    converter: Callable[[Any | None], Any | None] | None = None
    requires_value: bool = False


def _parse_voltage(raw: Any) -> float | None:
    """Try to normalise a voltage string into a float value."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().rstrip("Vv")
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _normalize_signal(raw: Any) -> float | None:
    """Convert a reported signal strength into a float percentage."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        trimmed = raw.strip().rstrip("%")
        try:
            return float(trimmed)
        except (TypeError, ValueError):
            return None
    return None


SENSOR_DESCRIPTIONS: tuple[ArmmeSensorEntityDescription, ...] = (
    ArmmeSensorEntityDescription(
        key="system_voltage",
        translation_key="system_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_extractor=lambda state: (
            state.com_status.system_voltage if state.com_status else None
        ),
        converter=_parse_voltage,
        requires_value=True,
    ),
    ArmmeSensorEntityDescription(
        key="com_version",
        translation_key="com_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_extractor=lambda state: (
            state.com_status.version_number if state.com_status else None
        ),
    ),
    ArmmeSensorEntityDescription(
        key="signal_sim1",
        translation_key="signal_sim1",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_extractor=lambda state: state.signal_sim1,
        converter=_normalize_signal,
    ),
    ArmmeSensorEntityDescription(
        key="signal_sim2",
        translation_key="signal_sim2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_extractor=lambda state: state.signal_sim2,
        converter=_normalize_signal,
    ),
)


class ArmmeSensor(CoordinatorEntity[ArmmeDataUpdateCoordinator], SensorEntity):
    """Generic ArmME sensor entity using an entity description."""

    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator: ArmmeDataUpdateCoordinator,
        api: ArmmeApi,
        description: ArmmeSensorEntityDescription,
    ) -> None:
        """Initialise the sensor wrapper."""
        super().__init__(coordinator)
        self.entity_description: ArmmeSensorEntityDescription = description
        serial = api.device.serial_no or str(api.device.device_id)
        self._attr_unique_id = f"{serial}-{description.key}"
        self._attr_device_info = _build_device_info(api)

    def _raw_value(self) -> Any | None:
        data = cast(ArmmeSystemState | None, getattr(self.coordinator, "data", None))
        if data is None:
            return None
        return self.entity_description.value_extractor(data)

    @property
    def available(self) -> bool:
        """Return availability based on coordinator status and data presence."""
        if not super().available:
            return False
        if self.entity_description.requires_value and self._raw_value() is None:
            return False
        return True

    @property
    def native_value(self) -> Any | None:
        """Return the sensor's native value using the configured converter."""
        raw = self._raw_value()
        converter = self.entity_description.converter
        if converter is not None:
            return converter(raw)
        return raw
