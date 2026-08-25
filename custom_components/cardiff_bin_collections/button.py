"""Buttons for Cardiff Bin Collections."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADDRESS, DOMAIN
from .coordinator import CardiffBinCollectionsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the manual refresh button."""
    async_add_entities([CardiffBinCollectionsRefreshButton(entry.runtime_data, entry)])


class CardiffBinCollectionsRefreshButton(
    CoordinatorEntity[CardiffBinCollectionsCoordinator], ButtonEntity
):
    """Request a rate-limited collection refresh."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:refresh"
    _attr_translation_key = "refresh"

    def __init__(
        self, coordinator: CardiffBinCollectionsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_ADDRESS],
            manufacturer="Cardiff Council",
            model="Waste collection service",
        )

    async def async_press(self) -> None:
        """Request a manual refresh."""
        await self.coordinator.async_manual_refresh()
