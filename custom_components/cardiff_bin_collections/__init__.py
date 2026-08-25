"""Cardiff Bin Collections integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_UPRN, DOMAIN
from .coordinator import CardiffBinCollectionsCoordinator

PLATFORMS = (Platform.BUTTON, Platform.SENSOR)

type CardiffBinCollectionsConfigEntry = ConfigEntry[CardiffBinCollectionsCoordinator]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Keep existing dashboard entity IDs stable while identifiers become portable."""
    if entry.version >= 2:
        return True

    old_prefix = f"{entry.data[CONF_UPRN]}_"
    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity.unique_id.startswith(old_prefix):
            entity_registry.async_update_entity(
                entity.entity_id,
                new_unique_id=f"{entry.entry_id}_{entity.unique_id.removeprefix(old_prefix)}",
            )

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if (DOMAIN, str(entry.data[CONF_UPRN])) in device.identifiers:
            device_registry.async_update_device(
                device.id, new_identifiers={(DOMAIN, entry.entry_id)}
            )

    hass.config_entries.async_update_entry(entry, version=2)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: CardiffBinCollectionsConfigEntry
) -> bool:
    """Set up Cardiff Bin Collections from a config entry."""
    coordinator = CardiffBinCollectionsCoordinator(hass, entry)
    needs_refresh = await coordinator.async_initialize()
    if needs_refresh:
        await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.async_start_schedule()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CardiffBinCollectionsConfigEntry
) -> bool:
    """Unload a Cardiff Bin Collections config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
