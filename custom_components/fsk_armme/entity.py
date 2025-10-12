"""Shared base entity helpers for the ArmME integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ArmmeApi
from .const import DOMAIN
from .coordinator import ArmmeDataUpdateCoordinator


def _build_device_info(api: ArmmeApi) -> DeviceInfo:
    """Return a DeviceInfo populated from the ArmME device metadata."""
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


class ArmmeEntity(CoordinatorEntity[ArmmeDataUpdateCoordinator]):
    """Base entity for all ArmME platforms."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ArmmeDataUpdateCoordinator,
        api: ArmmeApi,
        *,
        unique_id_suffix: str,
        name: str | None = None,
        translation_key: str | None = None,
    ) -> None:
        """Initialise the base entity."""
        super().__init__(coordinator)
        self._api = api
        self._serial = api.device.serial_no or str(api.device.device_id)
        self._attr_unique_id = f"{self._serial}-{unique_id_suffix}"
        self._attr_device_info = _build_device_info(api)
        if name is not None:
            self._attr_name = name
        if translation_key is not None:
            self._attr_translation_key = translation_key

    @property
    def available(self) -> bool:
        """Return availability based on the coordinator's last update status."""
        return self.coordinator.last_update_success and super().available

    @property
    def api(self) -> ArmmeApi:
        """Return the underlying API reference."""
        return self._api
