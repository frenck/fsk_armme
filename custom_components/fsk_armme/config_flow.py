"""Config flow for the ArmME integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_SERIAL,
    CONF_PANEL_CODE,
    CONF_PARTITION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_PARTITION,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
)
from .pyfskelec.client import ArmMEClient
from .pyfskelec.exceptions import ArmMEAuthError, ArmMERequestError
from .pyfskelec.models import DeviceSummary


def _default_update_interval_seconds() -> int:
    """Return the default polling interval expressed in seconds."""
    return int(DEFAULT_UPDATE_INTERVAL.total_seconds())


class ArmmeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ArmME."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise flow state."""
        self._client: ArmMEClient | None = None
        self._devices: list[DeviceSummary] = []
        self._username: str | None = None
        self._password: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where the user enters credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            try:
                self._client, self._devices = await self._async_login_and_list_devices(
                    self._username, self._password
                )
            except ArmMEAuthError:
                errors["base"] = "invalid_auth"
            except ArmMERequestError:
                errors["base"] = "cannot_connect"
            else:
                if not self._devices:
                    errors["base"] = "no_devices"
                else:
                    return await self.async_step_device()

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=self._username or ""): str,
                vol.Required(CONF_PASSWORD, default=""): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the target device and collect the panel code."""
        assert self._username and self._password

        errors: dict[str, str] = {}
        device_choices: dict[str, str] = {}
        for idx, device in enumerate(self._devices, start=1):
            label = device.name or device.serial_no or f"Device {idx}"
            device_choices[str(device.device_id)] = label
        default_device_id = next(iter(device_choices)) if device_choices else None

        if user_input is not None:
            device_id = int(user_input[CONF_DEVICE_ID])
            panel_code = user_input[CONF_PANEL_CODE]
            partition = int(user_input.get(CONF_PARTITION, DEFAULT_PARTITION))

            selected_device = next(
                (item for item in self._devices if item.device_id == device_id),
                None,
            )
            if selected_device is None:
                errors["base"] = "device_missing"
            else:
                unique_id = selected_device.serial_no or str(selected_device.device_id)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                data = {
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_PANEL_CODE: panel_code,
                    CONF_DEVICE_ID: selected_device.device_id,
                    CONF_DEVICE_SERIAL: selected_device.serial_no,
                    CONF_DEVICE_NAME: selected_device.name,
                    CONF_PARTITION: partition,
                }
                options = {
                    CONF_PARTITION: partition,
                    CONF_UPDATE_INTERVAL: _default_update_interval_seconds(),
                }
                if self._client:
                    # Close the temporary session.
                    self._client.s.close()
                    self._client = None
                title = (
                    selected_device.name
                    or selected_device.serial_no
                    or self._username
                    or "ArmME"
                )
                return self.async_create_entry(title=title, data=data, options=options)

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID, default=default_device_id): vol.In(
                    device_choices
                ),
                vol.Required(CONF_PANEL_CODE): str,
                vol.Optional(
                    CONF_PARTITION,
                    default=DEFAULT_PARTITION,
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            }
        )
        return self.async_show_form(
            step_id="device",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when credentials fail."""
        entry_id = self.context.get("entry_id")
        if entry_id:
            self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        if self._reauth_entry is None:
            return self.async_abort(reason="unknown")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a fresh password/panel code and update the entry."""
        assert self._reauth_entry is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            panel_code = user_input[CONF_PANEL_CODE]
            username = self._reauth_entry.data[CONF_USERNAME]

            try:
                client, _ = await self._async_login_and_list_devices(username, password)
            except ArmMEAuthError:
                errors["base"] = "invalid_auth"
            except ArmMERequestError:
                errors["base"] = "cannot_connect"
            else:
                client.s.close()
                new_data = dict(self._reauth_entry.data)
                new_data[CONF_PASSWORD] = password
                new_data[CONF_PANEL_CODE] = panel_code
                return self.async_update_reload_and_abort(
                    self._reauth_entry, data=new_data
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_PASSWORD): str,
                vol.Required(
                    CONF_PANEL_CODE,
                    default=self._reauth_entry.data.get(CONF_PANEL_CODE, ""),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    async def _async_login_and_list_devices(
        self, username: str, password: str
    ) -> tuple[ArmMEClient, list[DeviceSummary]]:
        """Login in an executor and return the authenticated client + devices."""

        def _login() -> tuple[ArmMEClient, list[DeviceSummary]]:
            client = ArmMEClient()
            client.login_password(username, password)
            devices = client.list_devices()
            return client, devices

        return await self.hass.async_add_executor_job(_login)

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow handler."""
        return ArmmeOptionsFlow(config_entry)


class ArmmeOptionsFlow(config_entries.OptionsFlow):
    """Handle options for the ArmME integration."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialise the options flow."""
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options form."""
        errors: dict[str, str] = {}

        current_partition = int(
            self._entry.options.get(
                CONF_PARTITION,
                self._entry.data.get(CONF_PARTITION, DEFAULT_PARTITION),
            )
        )
        current_interval = int(
            self._entry.options.get(
                CONF_UPDATE_INTERVAL, _default_update_interval_seconds()
            )
        )

        min_seconds = int(MIN_UPDATE_INTERVAL.total_seconds())

        if user_input is not None:
            partition = int(user_input[CONF_PARTITION])
            interval = int(user_input[CONF_UPDATE_INTERVAL])
            if interval < min_seconds:
                errors["base"] = "interval_too_short"
            else:
                options = {
                    CONF_PARTITION: partition,
                    CONF_UPDATE_INTERVAL: interval,
                }
                return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {
                vol.Required(CONF_PARTITION, default=current_partition): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=current_interval,
                ): vol.All(vol.Coerce(int)),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
