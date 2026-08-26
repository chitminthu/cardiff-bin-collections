"""Client for Cardiff Council's public waste web service."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    ADDRESS_LANGUAGE,
    ADDRESS_SEARCH_URL,
    AUTHORIZATION,
    BASE_URL,
    COLLECTIONS_URL,
    LANGUAGE,
    PURPOSE,
    TOKEN_URL,
)

TOKEN_PATTERN = re.compile(r"window\.verificationToken\s*=\s*'([^']+)'\s*;")
REQUEST_TIMEOUT = ClientTimeout(total=30, connect=10)


def normalize_postcode(postcode: str) -> str:
    """Return a postcode in a case- and spacing-independent form."""
    return re.sub(r"\s+", "", postcode).upper()


def format_postcode(postcode: str) -> str:
    """Return a postcode with one space before the final three characters."""
    compact = normalize_postcode(postcode)
    if len(compact) <= 3:
        return compact
    return f"{compact[:-3]} {compact[-3:]}"


class CardiffBinCollectionsError(Exception):
    """Base exception for Cardiff Bin Collections."""


class CardiffBinCollectionsConnectionError(CardiffBinCollectionsError):
    """Raised when Cardiff Council cannot be reached."""


class CardiffBinCollectionsResponseError(CardiffBinCollectionsError):
    """Raised when Cardiff Council returns an unexpected response."""


class CardiffBinCollectionsNoAddresses(CardiffBinCollectionsError):
    """Raised when an address search has no matches."""


@dataclass(frozen=True, slots=True)
class AddressMatch:
    """A Cardiff residential address search result."""

    uprn: int
    address: str


@dataclass(frozen=True, slots=True)
class Bin:
    """A bin included in a collection week."""

    bin_id: str
    waste_type: str
    collection_type: str
    image_url: str | None


@dataclass(frozen=True, slots=True)
class CollectionWeek:
    """One collection date and all bins collected on it."""

    collection_date: date
    day: str
    bins: tuple[Bin, ...]


@dataclass(frozen=True, slots=True)
class CollectionData:
    """Parsed collection response."""

    weeks: tuple[CollectionWeek, ...]
    has_glass_bin: bool

    def upcoming_weeks(self, on_or_after: date) -> tuple[CollectionWeek, ...]:
        """Return collection weeks that have not passed."""
        return tuple(week for week in self.weeks if week.collection_date >= on_or_after)

    def next_for_type(
        self, waste_type: str, on_or_after: date | None = None
    ) -> tuple[date, Bin] | None:
        """Return the earliest known collection for a waste type."""
        wanted = waste_type.casefold()
        for week in self.weeks:
            if on_or_after is not None and week.collection_date < on_or_after:
                continue
            for bin_item in week.bins:
                if bin_item.waste_type.casefold() == wanted:
                    return week.collection_date, bin_item
        return None


class CardiffBinCollectionsApi:
    """Retrieve addresses and waste collections from Cardiff Council."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _verification_token(self) -> str:
        """Retrieve a freshly generated verification token from the public page."""
        try:
            async with self._session.get(
                TOKEN_URL,
                headers={"Accept": "text/html,application/xhtml+xml"},
                timeout=REQUEST_TIMEOUT,
            ) as response:
                body = await response.text()
        except (ClientError, TimeoutError) as err:
            raise CardiffBinCollectionsConnectionError(
                "Unable to retrieve the Cardiff waste page"
            ) from err

        if response.status != 200:
            raise CardiffBinCollectionsResponseError(
                f"Waste page returned HTTP {response.status}"
            )

        match = TOKEN_PATTERN.search(body)
        if match is None:
            raise CardiffBinCollectionsResponseError(
                "The waste page did not contain a verification token"
            )
        return match.group(1)

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Authorization": AUTHORIZATION,
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": BASE_URL,
            "Referer": f"{TOKEN_URL}",
            "VerificationToken": token,
            "X-Requested-With": "XMLHttpRequest",
        }

    async def _post_json(self, url: str, payload: dict[str, Any]) -> Any:
        """POST JSON using a fresh page verification token, retrying once."""
        last_status: int | None = None
        for _attempt in range(2):
            token = await self._verification_token()
            try:
                async with self._session.post(
                    url,
                    headers=self._headers(token),
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    last_status = response.status
                    if response.status == 200:
                        try:
                            return await response.json(content_type=None)
                        except (ValueError, TypeError) as err:
                            raise CardiffBinCollectionsResponseError(
                                "Cardiff Council returned invalid JSON"
                            ) from err
                    await response.read()
            except (ClientError, TimeoutError) as err:
                raise CardiffBinCollectionsConnectionError(
                    "Unable to contact Cardiff Council"
                ) from err

        raise CardiffBinCollectionsResponseError(
            f"Cardiff Council returned HTTP {last_status}"
        )

    async def search_addresses(self, postcode: str) -> list[AddressMatch]:
        """Search Cardiff's residential gazetteer by postcode."""
        query = format_postcode(postcode)
        request = {
            "query": query,
            "language": ADDRESS_LANGUAGE,
            "purpose": PURPOSE,
        }

        # Cardiff has exposed both direct and wrapped request shapes through
        # revisions of its web-form proxy, so support either without asking
        # the user to know which one is active.
        for payload in (request, {"request": request}):
            try:
                data = await self._post_json(ADDRESS_SEARCH_URL, payload)
            except CardiffBinCollectionsResponseError:
                continue

            matches = parse_address_matches(data, query)

            if matches:
                return matches

        raise CardiffBinCollectionsNoAddresses(
            f"No residential addresses found for {query}"
        )

    async def collections(self, uprn: int) -> CollectionData:
        """Retrieve and parse collection weeks for a UPRN."""
        data = await self._post_json(
            COLLECTIONS_URL,
            {
                "systemReference": "web",
                "language": LANGUAGE,
                "uprn": int(uprn),
                "includecancelled": True,
            },
        )
        return parse_collection_data(data)


def parse_address_matches(data: Any, requested_postcode: str) -> list[AddressMatch]:
    """Parse only address results that exactly match the requested postcode."""
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        return []

    requested = normalize_postcode(requested_postcode)
    matches: list[AddressMatch] = []
    for item in data["results"]:
        try:
            uprn = int(item["uprn"])
            address = str(item["address"]).strip()
            result_postcode = str(item["postcode"])
        except (KeyError, TypeError, ValueError):
            continue
        if address and normalize_postcode(result_postcode) == requested:
            matches.append(AddressMatch(uprn=uprn, address=address))
    return matches


def parse_collection_data(data: Any) -> CollectionData:
    """Validate and parse the Cardiff collection JSON response."""
    if not isinstance(data, dict) or not isinstance(data.get("collectionWeeks"), list):
        raise CardiffBinCollectionsResponseError(
            "Collection response did not contain collectionWeeks"
        )

    weeks: list[CollectionWeek] = []
    for raw_week in data["collectionWeeks"]:
        try:
            collection_date = datetime.fromisoformat(raw_week["date"]).date()
            day = str(raw_week["day"])
            raw_bins = raw_week["bins"]
        except (KeyError, TypeError, ValueError) as err:
            raise CardiffBinCollectionsResponseError(
                "A collection week was malformed"
            ) from err

        bins: list[Bin] = []
        for raw_bin in raw_bins:
            try:
                bins.append(
                    Bin(
                        bin_id=str(raw_bin["binId"]),
                        waste_type=str(raw_bin["type"]),
                        collection_type=str(raw_bin["collectionType"]),
                        image_url=(
                            str(raw_bin["imageUrl"])
                            if raw_bin.get("imageUrl")
                            else None
                        ),
                    )
                )
            except (KeyError, TypeError) as err:
                raise CardiffBinCollectionsResponseError(
                    "A bin entry was malformed"
                ) from err

        weeks.append(
            CollectionWeek(
                collection_date=collection_date,
                day=day,
                bins=tuple(bins),
            )
        )

    weeks.sort(key=lambda item: item.collection_date)
    return CollectionData(
        weeks=tuple(weeks),
        has_glass_bin=bool(data.get("hasGlassBin", False)),
    )


def serialize_collection_data(data: CollectionData) -> dict[str, Any]:
    """Convert collection data to the council API's JSON-compatible shape."""
    return {
        "collectionWeeks": [
            {
                "week": index,
                "date": week.collection_date.isoformat(),
                "day": week.day,
                "bins": [
                    {
                        "binId": bin_item.bin_id,
                        "imageUrl": bin_item.image_url,
                        "type": bin_item.waste_type,
                        "collectionType": bin_item.collection_type,
                    }
                    for bin_item in week.bins
                ],
            }
            for index, week in enumerate(data.weeks, start=1)
        ],
        "hasGlassBin": data.has_glass_bin,
    }
