"""DataUpdateCoordinator for Tasman Bridge."""
import asyncio
import re
import logging
from datetime import date, datetime, time, timedelta

import aiohttp
from bs4 import BeautifulSoup

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SCRAPE_URL,
    UPDATE_INTERVAL,
    COLOR_MAP,
    DEFAULT_COLOR,
    REQUEST_HEADERS,
    COLOR_SEPARATOR_PATTERN,
    STORAGE_VERSION,
    STORAGE_KEY,
    FETCH_ATTEMPTS,
    FETCH_BACKOFF,
)

_LOGGER = logging.getLogger(__name__)

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, 
    "may": 5, "june": 6, "july": 7, "august": 8, 
    "september": 9, "october": 10, "november": 11, "december": 12
}

class TasmanBridgeCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Tasman Bridge data."""

    def __init__(self, hass: HomeAssistant):
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.session = async_get_clientsession(hass)
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def _async_update_data(self):
        """Fetch data from website, falling back to the last good schedule."""
        try:
            html = await self._async_fetch_html()

            current_year = dt_util.now().year
            events = await self.hass.async_add_executor_job(self._parse_html, html, current_year)
        except Exception as err:
            # A transient failure (the site WAF returning 403, a timeout) should
            # not blank out every entity. Reuse what we already have, or what we
            # persisted on a previous run if this is a restart.
            cached = self.data or await self._async_load_cache()
            if cached:
                _LOGGER.warning(
                    "Tasman Bridge fetch failed (%s); serving %d cached events",
                    err,
                    len(cached),
                )
                return cached
            raise UpdateFailed(f"Error communicating with API: {err}")

        # Only persist a real schedule; an empty parse means the page changed
        # shape and should not wipe a good cache.
        if events:
            await self._async_save_cache(events)

        return events

    async def _async_fetch_html(self):
        """Fetch the page, retrying through Cloudflare's intermittent challenge."""
        last_err = None

        for attempt in range(1, FETCH_ATTEMPTS + 1):
            try:
                async with self.session.get(
                    SCRAPE_URL,
                    headers=REQUEST_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response.raise_for_status()
                    return await response.text()
            except Exception as err:
                last_err = err
                if attempt < FETCH_ATTEMPTS:
                    _LOGGER.debug(
                        "Tasman Bridge fetch attempt %d/%d failed (%s); retrying",
                        attempt,
                        FETCH_ATTEMPTS,
                        err,
                    )
                    await asyncio.sleep(FETCH_BACKOFF * attempt)

        raise last_err

    async def _async_load_cache(self):
        """Return the persisted schedule, or None if there isn't a usable one."""
        stored = await self._store.async_load()
        if not stored:
            return None

        events = []
        for raw in stored.get("events", []):
            event = dict(raw)
            event["active_start"] = dt_util.parse_datetime(raw.get("active_start", ""))
            event["active_end"] = dt_util.parse_datetime(raw.get("active_end", ""))
            if event["active_start"] and event["active_end"]:
                events.append(event)

        return events or None

    async def _async_save_cache(self, events):
        """Persist the schedule, with datetimes flattened to ISO strings."""
        await self._store.async_save({
            "events": [
                {
                    **event,
                    "active_start": event["active_start"].isoformat(),
                    "active_end": event["active_end"].isoformat(),
                }
                for event in events
            ]
        })

    def _parse_html(self, html, current_year):
        """Parse the HTML table synchronously using BeautifulSoup."""
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        
        events = []
        if not table:
            _LOGGER.warning(
                "No schedule table found at %s - the page layout may have changed",
                SCRAPE_URL,
            )
            return events

        tz = dt_util.DEFAULT_TIME_ZONE

        for row in table.find_all("tr")[1:]:  # Skip header row
            cols = row.find_all("td")
            if len(cols) >= 3:
                date_str = cols[0].get_text(strip=True)
                purpose = cols[1].get_text(strip=True)
                color_raw = cols[2].get_text(strip=True)

                color_names, color_hexes = self._parse_colors(color_raw)
                start_date, end_date = self._parse_date_string(date_str, current_year)

                if start_date and end_date:
                    # An event runs from 12:00 PM on the start date to 12:00 PM on the end date
                    active_start = datetime.combine(start_date, time(12, 0), tzinfo=tz)
                    active_end = datetime.combine(end_date, time(12, 0), tzinfo=tz)

                    events.append({
                        "date_str": date_str,
                        "purpose": purpose,
                        "color_name": "/".join(n.title() for n in color_names),
                        "color_names": [n.title() for n in color_names],
                        "color_hex": color_hexes[0],
                        "color_hexes": color_hexes,
                        "active_start": active_start,
                        "active_end": active_end
                    })

        # Ensure sorted chronologically
        events.sort(key=lambda x: x["active_start"])
        return events

    def _parse_colors(self, color_raw):
        """Split a Colour cell into parallel lists of names and hex values.

        The cell is free text and may name several colours, e.g.
        "Pink/white/blue". Unrecognised words are logged and skipped, so a new
        colour appearing on the website degrades to the ones we do know rather
        than silently reporting the default.
        """
        color_raw = color_raw.replace("\xa0", " ").strip().lower()

        # "Application pending" rows have no colour allocated yet
        if not color_raw or "pending" in color_raw:
            return [DEFAULT_COLOR], [COLOR_MAP[DEFAULT_COLOR]]

        names = []
        hexes = []
        for token in re.split(COLOR_SEPARATOR_PATTERN, color_raw):
            token = token.strip()
            if not token:
                continue
            if token in COLOR_MAP:
                names.append(token)
                hexes.append(COLOR_MAP[token])
            else:
                _LOGGER.warning(
                    "Unrecognised Tasman Bridge colour %r (in cell %r); "
                    "add it to COLOR_MAP in const.py",
                    token,
                    color_raw,
                )

        if not hexes:
            return [DEFAULT_COLOR], [COLOR_MAP[DEFAULT_COLOR]]

        return names, hexes

    def _parse_date_string(self, date_str, current_year):
        """Convert '15 - 17 March 2026' into start and end date objects."""
        # Clean formatting inconsistencies
        date_str = date_str.replace('\xa0', ' ').replace('–', '-').strip()
        
        # Match ranges: "15 - 17 March 2026" or "31 March - 2 April 2026"
        m_range = re.search(r"(\d+)\s*([A-Za-z]+)?\s*-\s*(\d+)\s+([A-Za-z]+)\s*(\d{4})?", date_str)
        if m_range:
            d1, m1, d2, m2, y = m_range.groups()
            year = int(y) if y else current_year
            month2 = MONTHS.get(m2.lower(), 1)
            month1 = MONTHS.get(m1.lower(), month2) if m1 else month2
            
            # Handle year wrapping (e.g., 28 Dec - 3 Jan)
            year1 = year
            if month1 > month2:
                year1 = year - 1
                
            return date(year1, month1, int(d1)), date(year, month2, int(d2))

        # Match single days: "31 May"
        m_single = re.search(r"(\d+)\s+([A-Za-z]+)\s*(\d{4})?", date_str)
        if m_single:
            d1, m1, y = m_single.groups()
            year = int(y) if y else current_year
            month1 = MONTHS.get(m1.lower(), 1)
            start = date(year, month1, int(d1))
            end = start + timedelta(days=1)
            return start, end

        return None, None
