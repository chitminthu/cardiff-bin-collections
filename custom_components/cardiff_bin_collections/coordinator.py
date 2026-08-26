"""Data coordinator for Cardiff Bin Collections."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    CardiffBinCollectionsApi,
    CardiffBinCollectionsError,
    CollectionData,
    parse_collection_data,
    serialize_collection_data,
)
from .const import (
    CACHE_MAX_AGE,
    CONF_UPRN,
    DOMAIN,
    MANUAL_REFRESH_MIN_INTERVAL,
    PENDING_COLLECTIONS,
    RETRY_DELAYS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .schedule import SUNDAY, next_sunday_refresh, refresh_time_for_uprn

_LOGGER = logging.getLogger(__name__)


class CardiffBinCollectionsCoordinator(DataUpdateCoordinator[CollectionData]):
    """Fetch and persist Cardiff collection data at a council-friendly interval."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            config_entry=entry,
        )
        self._api = CardiffBinCollectionsApi(async_get_clientsession(hass))
        self._uprn = int(entry.data[CONF_UPRN])
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY.format(entry_id=entry.entry_id)
        )
        self._last_success: datetime | None = None
        self._last_manual_refresh: datetime | None = None
        self._last_error: str | None = None
        self._data_source = "none"
        self._retry_count = 0
        self._cancel_retry: Callable[[], None] | None = None

    async def async_initialize(self) -> bool:
        """Restore validated setup data or a fresh persistent cache."""
        pending = self.hass.data.setdefault(PENDING_COLLECTIONS, {}).pop(
            str(self._uprn), None
        )
        if pending is not None:
            self._last_success = dt_util.utcnow()
            self._data_source = "live"
            self.async_set_updated_data(pending)
            await self._async_save_cache(pending)
            return False

        cached = await self._store.async_load()
        if not cached or int(cached.get("uprn", 0)) != self._uprn:
            return True

        try:
            data = parse_collection_data(cached["data"])
            saved_at = dt_util.parse_datetime(cached["saved_at"])
        except (KeyError, TypeError, ValueError, CardiffBinCollectionsError):
            _LOGGER.warning("Ignoring an invalid Cardiff collection cache")
            return True
        if saved_at is None:
            return True

        self._last_success = saved_at
        self._data_source = "cache"
        self.async_set_updated_data(data)
        return self._cache_needs_refresh(data, saved_at)

    def async_start_schedule(self) -> None:
        """Schedule weekly retrieval and local midnight date rollover."""
        refresh_time = refresh_time_for_uprn(self._uprn)
        cancel_refresh = async_track_time_change(
            self.hass,
            self._async_scheduled_refresh,
            hour=refresh_time.hour,
            minute=refresh_time.minute,
            second=0,
        )
        self.config_entry.async_on_unload(cancel_refresh)
        cancel_rollover = async_track_time_change(
            self.hass,
            self._async_midnight_rollover,
            hour=0,
            minute=0,
            second=5,
        )
        self.config_entry.async_on_unload(cancel_rollover)

    @callback
    def _async_midnight_rollover(self, _now: datetime) -> None:
        """Recalculate date sensors from the cache without a council request."""
        if self.data is not None:
            self.async_set_updated_data(self.data)

    async def _async_scheduled_refresh(self, now: datetime) -> None:
        """Refresh only on Sunday when the daily time listener fires."""
        if now.weekday() != SUNDAY:
            return
        self._retry_count = 0
        await self.async_request_refresh()

    async def _async_update_data(self) -> CollectionData:
        """Fetch new data while retaining the cache on a temporary failure."""
        try:
            data = await self._api.collections(self._uprn)
            if not data.weeks:
                raise CardiffBinCollectionsError(
                    "Cardiff Council returned no upcoming collections"
                )
        except CardiffBinCollectionsError as err:
            self._last_error = str(err)
            if self.data is None:
                raise UpdateFailed(str(err)) from err
            self._data_source = "cache"
            self._schedule_retry()
            _LOGGER.warning("Collection refresh failed; retaining cached data: %s", err)
            return self.data

        self._cancel_pending_retry()
        self._retry_count = 0
        self._last_success = dt_util.utcnow()
        self._last_error = None
        self._data_source = "live"
        await self._async_save_cache(data)
        return data

    async def async_manual_refresh(self) -> None:
        """Refresh on request, limited to once per hour per config entry."""
        now = dt_util.utcnow()
        if (
            self._last_manual_refresh is not None
            and now - self._last_manual_refresh < MANUAL_REFRESH_MIN_INTERVAL
        ):
            raise HomeAssistantError(
                "Manual refresh is available once per hour. Please try again later."
            )
        self._last_manual_refresh = now
        await self.async_request_refresh()
        if self._last_error is not None:
            raise HomeAssistantError(self._last_error)

    @property
    def status_attributes(self) -> dict[str, Any]:
        """Return useful refresh and cache diagnostics for entities."""
        now = dt_util.utcnow()
        return {
            "data_source": self._data_source,
            "last_successful_refresh": self._last_success,
            "next_scheduled_refresh": next_sunday_refresh(
                now, dt_util.get_time_zone(self.hass.config.time_zone), self._uprn
            ),
            "cache_age_hours": (
                round((now - self._last_success).total_seconds() / 3600, 1)
                if self._last_success is not None
                else None
            ),
            "last_refresh_error": self._last_error,
        }

    def _cache_needs_refresh(
        self, data: CollectionData, saved_at: datetime
    ) -> bool:
        """Return whether cached data is too old or has no future dates."""
        now = dt_util.utcnow()
        has_future_collection = any(
            week.collection_date >= now.date() for week in data.weeks
        )
        return now - saved_at >= CACHE_MAX_AGE or not has_future_collection

    async def _async_save_cache(self, data: CollectionData) -> None:
        """Persist successful collection data in Home Assistant storage."""
        saved_at = self._last_success or dt_util.utcnow()
        await self._store.async_save(
            {
                "uprn": self._uprn,
                "saved_at": saved_at.isoformat(),
                "data": serialize_collection_data(data),
            }
        )

    def _schedule_retry(self) -> None:
        """Schedule Sunday and Monday recovery attempts after a failure."""
        if self._cancel_retry is not None or self._retry_count >= len(RETRY_DELAYS):
            return
        delay = RETRY_DELAYS[self._retry_count]
        self._retry_count += 1
        self._cancel_retry = async_call_later(
            self.hass, delay, self._async_retry_refresh
        )

    async def _async_retry_refresh(self, _now: datetime) -> None:
        self._cancel_retry = None
        await self.async_request_refresh()

    def _cancel_pending_retry(self) -> None:
        if self._cancel_retry is not None:
            self._cancel_retry()
            self._cancel_retry = None
