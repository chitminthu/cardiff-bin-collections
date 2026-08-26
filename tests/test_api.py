"""Tests for the Cardiff API parser."""

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import pytest


def _load_api_module():
    """Load the API module without importing Home Assistant."""
    root = Path(__file__).parents[1] / "custom_components" / "cardiff_bin_collections"
    package = types.ModuleType("cardiff_bin_collections")
    package.__path__ = [str(root)]
    sys.modules["cardiff_bin_collections"] = package
    for name in ("const", "api"):
        spec = importlib.util.spec_from_file_location(
            f"cardiff_bin_collections.{name}", root / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return sys.modules["cardiff_bin_collections.api"]


api = _load_api_module()


SAMPLE = {
    "language": "en-GB",
    "collectionWeeks": [
        {
            "week": 1,
            "date": "2026-08-25T00:00:00",
            "day": "Tuesday",
            "bins": [
                {
                    "binId": "25 Food Caddy",
                    "imageUrl": "https://example.invalid/FoodCaddy.png",
                    "type": "Food",
                    "collectionType": "Standard",
                },
                {
                    "binId": "BlueRedSack",
                    "imageUrl": None,
                    "type": "Recycling",
                    "collectionType": "Standard",
                },
            ],
        },
        {
            "week": 2,
            "date": "2026-09-01T00:00:00",
            "day": "Tuesday",
            "bins": [
                {
                    "binId": "140 Residual Bin",
                    "imageUrl": None,
                    "type": "General",
                    "collectionType": "Standard",
                }
            ],
        },
    ],
    "hasGlassBin": True,
}


def test_extracts_verification_token_pattern() -> None:
    html = "<script>window.verificationToken = 'fresh-token';</script>"
    assert api.TOKEN_PATTERN.search(html).group(1) == "fresh-token"


def test_parses_collection_dates_and_bins() -> None:
    result = api.parse_collection_data(SAMPLE)
    assert result.has_glass_bin is True
    assert result.weeks[0].collection_date == date(2026, 8, 25)
    assert [item.waste_type for item in result.weeks[0].bins] == [
        "Food",
        "Recycling",
    ]
    assert result.next_for_type("general")[0] == date(2026, 9, 1)
    assert result.next_for_type("glass") is None


@pytest.mark.parametrize(
    ("today", "expected_dates"),
    [
        (date(2026, 8, 24), [date(2026, 8, 25), date(2026, 9, 1)]),
        (date(2026, 8, 25), [date(2026, 8, 25), date(2026, 9, 1)]),
        (date(2026, 8, 26), [date(2026, 9, 1)]),
        (date(2026, 9, 2), []),
    ],
)
def test_upcoming_weeks_exclude_expired_dates(
    today: date, expected_dates: list[date]
) -> None:
    result = api.parse_collection_data(SAMPLE)

    assert [week.collection_date for week in result.upcoming_weeks(today)] == (
        expected_dates
    )


def test_waste_type_date_respects_today() -> None:
    result = api.parse_collection_data(SAMPLE)

    assert result.next_for_type("food", date(2026, 8, 26)) is None
    assert result.next_for_type("general", date(2026, 8, 26))[0] == date(2026, 9, 1)


@pytest.mark.asyncio
async def test_verification_token_request_has_a_timeout() -> None:
    class TimeoutSession:
        def get(self, *args, **kwargs):
            assert kwargs["timeout"] is api.REQUEST_TIMEOUT
            raise TimeoutError

    client = api.CardiffBinCollectionsApi(TimeoutSession())

    with pytest.raises(api.CardiffBinCollectionsConnectionError):
        await client._verification_token()


def test_rejects_malformed_collection_response() -> None:
    with pytest.raises(api.CardiffBinCollectionsResponseError):
        api.parse_collection_data({"language": "en-GB"})


def test_collection_cache_round_trip() -> None:
    original = api.parse_collection_data(SAMPLE)
    restored = api.parse_collection_data(api.serialize_collection_data(original))
    assert restored == original


def test_formats_postcodes_consistently() -> None:
    assert api.format_postcode("cf99 9zz") == "CF99 9ZZ"
    assert api.format_postcode("CF999ZZ") == "CF99 9ZZ"
    assert api.normalize_postcode(" cF99  9Zz ") == "CF999ZZ"


def test_address_results_require_an_exact_postcode_match() -> None:
    response = {
        "results": [
            {
                "uprn": 1001,
                "address": "1 Example Street, Cardiff, CF99 9ZZ",
                "postcode": "cf99 9zz",
            },
            {
                "uprn": 1002,
                "address": "2 Other Street, Cardiff, CF98 8YY",
                "postcode": "CF98 8YY",
            },
        ]
    }

    matches = api.parse_address_matches(response, "CF999ZZ")

    assert matches == [
        api.AddressMatch(
            uprn=1001,
            address="1 Example Street, Cardiff, CF99 9ZZ",
        )
    ]


def test_fuzzy_council_result_is_rejected() -> None:
    response = {
        "results": [
            {
                "uprn": 1002,
                "address": "2 Other Street, Cardiff, CF98 8YY",
                "postcode": "CF98 8YY",
            }
        ]
    }

    assert api.parse_address_matches(response, "CF99 9ZZ") == []
