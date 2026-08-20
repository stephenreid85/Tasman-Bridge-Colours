"""Constants for the Tasman Bridge integration."""
from datetime import timedelta

DOMAIN = "tasman_bridge"

SCRAPE_URL = "https://www.transport.tas.gov.au/road_permits/permits_and_bookings/tasman_bridge_lights"

# Update interval serves as a fallback. 
# We explicitly schedule targeted updates at 11:30 AM and 12:00 PM in __init__.py
UPDATE_INTERVAL = timedelta(hours=6)

# Map government text to Hex values.
# Includes common synonyms, since the published schedule is free text and the
# wording varies between entries (e.g. "violet" vs "purple", "cyan" vs "aqua").
COLOR_MAP = {
    "red": "#FF0000",
    "orange": "#FFA500",
    "amber": "#FFBF00",
    "yellow": "#FFD700",
    "gold": "#FFD700",
    "lime": "#BFFF00",
    "green": "#00FF00",
    "teal": "#008080",
    "turquoise": "#40E0D0",
    "cyan": "#00FFFF",
    "aqua": "#00FFFF",
    "blue": "#0000FF",
    "indigo": "#4B0082",
    "violet": "#8A2BE2",
    "purple": "#8A2BE2",
    "magenta": "#FF00FF",
    "rose": "#FF007F",
    "pink": "#FFC0CB",
    "silver": "#C0C0C0",
    "white": "#FFFFFF",
    "warm white": "#FDF4DC"
}

# A single Colour cell may list several colours, e.g. "Pink/white/blue" or
# "green, gold and white". Split on these separators; note that we never split
# on plain spaces, so multi-word names like "warm white" survive intact.
COLOR_SEPARATOR_PATTERN = r"\s*(?:[/|,+&]|\band\b)\s*"

# Persisted copy of the last successful scrape. The published schedule changes
# rarely, so cached events stay correct for days and let the integration ride
# out a failed fetch instead of dropping every entity to unavailable.
STORAGE_VERSION = 1
STORAGE_KEY = "tasman_bridge_schedule"

DEFAULT_COLOR = "warm white"
DEFAULT_COLOR_HEX = COLOR_MAP[DEFAULT_COLOR]

# The transport.tas.gov.au WAF returns 403 for the default aiohttp User-Agent,
# so present as a normal browser.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}
