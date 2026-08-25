"""Sensors for Cardiff Bin Collections."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CollectionData, CollectionWeek
from .const import CONF_ADDRESS, DOMAIN, WASTE_TYPES
from .coordinator import CardiffBinCollectionsCoordinator

WASTE_ICONS = {
    "general": "mdi:trash-can",
    "recycling": "mdi:recycle",
    "food": "mdi:food-apple",
    "garden": "mdi:leaf",
    "glass": "mdi:bottle-soda",
    "hygiene": "mdi:shower-head",
    "christmas tree": "mdi:pine-tree",
}

RARE_WASTE_TYPES = {"hygiene", "christmas tree"}


@dataclass(frozen=True, kw_only=True)
class CardiffBinSensorDescription(SensorEntityDescription):
    """Describe one Cardiff collection sensor."""

    value_fn: Callable[[CollectionData], date | None]
    attributes_fn: Callable[[CollectionData], dict[str, Any]]


def _week_attributes(week: CollectionWeek | None) -> dict[str, Any]:
    if week is None:
        return {}
    return {
        "day": week.day,
        "bins": [item.waste_type for item in week.bins],
        "bin_ids": [item.bin_id for item in week.bins],
        "collection_types": [item.collection_type for item in week.bins],
        "bin_details": [
            {
                "type": item.waste_type,
                "bin_id": item.bin_id,
                "collection_type": item.collection_type,
                "image_url": item.image_url,
            }
            for item in week.bins
        ],
    }


def _week_at(index: int) -> CardiffBinSensorDescription:
    def week(data: CollectionData) -> CollectionWeek | None:
        return data.weeks[index] if len(data.weeks) > index else None

    return CardiffBinSensorDescription(
        key="next_collection" if index == 0 else "following_collection",
        translation_key="next_collection" if index == 0 else "following_collection",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-arrow-right",
        value_fn=lambda data: week(data).collection_date if week(data) else None,
        attributes_fn=lambda data: _week_attributes(week(data)),
    )


def _type_description(waste_type: str) -> CardiffBinSensorDescription:
    key = waste_type.replace(" ", "_")

    def match(data: CollectionData):
        return data.next_for_type(waste_type)

    return CardiffBinSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DATE,
        icon=WASTE_ICONS.get(waste_type, "mdi:trash-can"),
        entity_registry_enabled_default=waste_type not in RARE_WASTE_TYPES,
        value_fn=lambda data: match(data)[0] if match(data) else None,
        attributes_fn=lambda data: (
            {
                "bin_id": match(data)[1].bin_id,
                "collection_type": match(data)[1].collection_type,
                "image_url": match(data)[1].image_url,
            }
            if match(data)
            else {}
        ),
    )


SENSOR_DESCRIPTIONS = (
    _week_at(0),
    _week_at(1),
    *(_type_description(waste_type) for waste_type in WASTE_TYPES),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Cardiff bin collection sensors."""
    coordinator: CardiffBinCollectionsCoordinator = entry.runtime_data
    async_add_entities(
        CardiffBinCollectionSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class CardiffBinCollectionSensor(
    CoordinatorEntity[CardiffBinCollectionsCoordinator], SensorEntity
):
    """A Cardiff bin collection date sensor."""

    entity_description: CardiffBinSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CardiffBinCollectionsCoordinator,
        entry: ConfigEntry,
        description: CardiffBinSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_ADDRESS],
            manufacturer="Cardiff Council",
            model="Waste collection service",
        )

    @property
    def native_value(self) -> date | None:
        """Return the collection date."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return collection details."""
        return {
            **self.entity_description.attributes_fn(self.coordinator.data),
            **self.coordinator.status_attributes,
        }
