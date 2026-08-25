"""Tests for council-friendly weekly scheduling."""

import importlib.util
import sys
import types
from datetime import UTC, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo


def _load_schedule_module():
    root = Path(__file__).parents[1] / "custom_components" / "cardiff_bin_collections"
    package = types.ModuleType("cardiff_bin_collections")
    package.__path__ = [str(root)]
    sys.modules["cardiff_bin_collections"] = package
    for name in ("const", "schedule"):
        spec = importlib.util.spec_from_file_location(
            f"cardiff_bin_collections.{name}", root / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return sys.modules["cardiff_bin_collections.schedule"]


schedule = _load_schedule_module()


def test_refresh_time_is_stable_and_in_window() -> None:
    assert schedule.refresh_time_for_uprn(1) == time(5, 1)
    assert schedule.refresh_time_for_uprn(1) == (
        schedule.refresh_time_for_uprn(1)
    )


def test_next_refresh_uses_cardiff_sunday_time() -> None:
    now = datetime(2026, 8, 25, 9, tzinfo=UTC)
    result = schedule.next_sunday_refresh(
        now, ZoneInfo("Europe/London"), 1
    )
    assert result == datetime(2026, 8, 30, 4, 1, tzinfo=UTC)


def test_next_refresh_rolls_forward_after_sunday_slot() -> None:
    now = datetime(2026, 8, 30, 8, tzinfo=UTC)
    result = schedule.next_sunday_refresh(
        now, ZoneInfo("Europe/London"), 1
    )
    assert result == datetime(2026, 9, 6, 4, 1, tzinfo=UTC)
