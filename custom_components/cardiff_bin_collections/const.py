"""Constants for Cardiff Bin Collections."""

from datetime import timedelta

DOMAIN = "cardiff_bin_collections"

CONF_UPRN = "uprn"
CONF_ADDRESS = "address"
CONF_POSTCODE = "postcode"

PENDING_COLLECTIONS = f"{DOMAIN}_pending_collections"
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.{{entry_id}}"

CACHE_MAX_AGE = timedelta(days=7)
MANUAL_REFRESH_MIN_INTERVAL = timedelta(hours=1)
RETRY_DELAYS = (timedelta(hours=6), timedelta(hours=18))
REFRESH_WINDOW_START_HOUR = 5
REFRESH_WINDOW_MINUTES = 4 * 60

UK_POSTCODE_PATTERN = r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$"

BASE_URL = "https://app-cprd-webformsproxy-prd.azurewebsites.net"
TOKEN_URL = f"{BASE_URL}/WASTE_wc"
ADDRESS_SEARCH_URL = (
    f"{BASE_URL}/api/Gazetteer/api/Search/LLPG/Residential"
)
COLLECTIONS_URL = (
    f"{BASE_URL}/api/WasteManagement/api/WasteCollection"
)

AUTHORIZATION = "Bearer cardiff"
LANGUAGE = "eng"
ADDRESS_LANGUAGE = "en-GB"
PURPOSE = "WasteCalendar"

WASTE_TYPES = (
    "general",
    "recycling",
    "food",
    "garden",
    "glass",
    "hygiene",
    "christmas tree",
)
