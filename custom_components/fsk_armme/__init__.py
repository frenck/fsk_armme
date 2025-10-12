"""Home Assistant integration for ArmME alarm systems."""

from __future__ import annotations

from datetime import timedelta
import logging

from pyfskelec.exceptions import ArmMEAuthError, ArmMERequestError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .api import ArmmeApi
from .const import (
    CONF_DEVICE_ID,
    CONF_PANEL_CODE,
    CONF_PARTITION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_PARTITION,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
    PLATFORMS,
)
from .coordinator import ArmmeDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the ArmME integration (YAML not supported)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ArmME from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    data = entry.data

    api = ArmmeApi(
        hass,
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        panel_code=data[CONF_PANEL_CODE],
        device_id=data[CONF_DEVICE_ID],
    )

    try:
        await api.async_initialize()
    except ArmMEAuthError as err:
        raise ConfigEntryAuthFailed(err) from err
    except ArmMERequestError as err:
        raise ConfigEntryNotReady(err) from err

    coordinator = ArmmeDataUpdateCoordinator(
        hass,
        api=api,
        partition=_get_partition(entry),
        update_interval=_get_update_interval(entry),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:  # pylint: disable=broad-except
        raise ConfigEntryNotReady(err) from err

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an ArmME config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data:
        api: ArmmeApi = data["api"]
        await api.async_shutdown()

    return True


def _get_update_interval(entry: ConfigEntry) -> timedelta:
    """Return the configured update interval."""
    option_value = entry.options.get(CONF_UPDATE_INTERVAL)
    if option_value is None:
        return DEFAULT_UPDATE_INTERVAL
    seconds = int(option_value)
    interval = timedelta(seconds=seconds)
    if interval < MIN_UPDATE_INTERVAL:
        _LOGGER.debug(
            "Configured polling interval %s is below minimum; clamping to %s",
            interval,
            MIN_UPDATE_INTERVAL,
        )
        return MIN_UPDATE_INTERVAL
    return interval


def _get_partition(entry: ConfigEntry) -> int:
    """Return the configured partition, falling back to defaults."""
    if CONF_PARTITION in entry.options:
        return int(entry.options[CONF_PARTITION])
    if CONF_PARTITION in entry.data:
        return int(entry.data[CONF_PARTITION])
    return DEFAULT_PARTITION


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
