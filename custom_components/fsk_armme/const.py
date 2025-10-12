"""Constants for the ArmME integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "fsk_armme"

CONF_PANEL_CODE = "panel_code"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_SERIAL = "device_serial"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_PARTITION = "partition"

DEFAULT_PARTITION = 1
DEFAULT_UPDATE_INTERVAL = timedelta(seconds=30)
MIN_UPDATE_INTERVAL = timedelta(seconds=15)

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
]
