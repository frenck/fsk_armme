"""Data update coordinator for the ArmME integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ArmmeApi, ArmmeSystemState
from .pyfskelec.exceptions import ArmMEAuthError, ArmMERequestError

_LOGGER = logging.getLogger(__name__)


class ArmmeDataUpdateCoordinator(DataUpdateCoordinator[ArmmeSystemState]):
    """Coordinator polling the ArmME API for the latest system state."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        api: ArmmeApi,
        partition: int,
        update_interval: timedelta,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="ArmME",
            update_interval=update_interval,
        )
        self.api = api
        self.partition = int(partition)

    async def _async_update_data(self) -> ArmmeSystemState:
        """Fetch state from the underlying API."""
        try:
            return await self.api.async_fetch_state(partition=self.partition)
        except ArmMEAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except ArmMERequestError as err:
            raise UpdateFailed(str(err)) from err
