"""The Tasman Bridge integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.frontend import DATA_THEMES
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, DEFAULT_COLOR_HEX
from .coordinator import TasmanBridgeCoordinator

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tasman Bridge from a config entry."""
    coordinator = TasmanBridgeCoordinator(hass)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register the integration as a unified Device in HA
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Tasman Bridge",
        manufacturer="Tasmanian Government",
        model="Lighting Schedule",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def update_theme_and_state(*args):
        """Calculate the active color and update the HA Theme."""
        current_time = dt_util.now()
        events = coordinator.data or []
        
        active_hex = DEFAULT_COLOR_HEX
        accent_hex = DEFAULT_COLOR_HEX
        for event in events:
            # Check if current time falls within the 12:00 PM to 12:00 PM window
            if event["active_start"] <= current_time < event["active_end"]:
                hexes = event["color_hexes"]
                active_hex = hexes[0]
                # On multi-colour nights (e.g. "Pink/white/blue") the second
                # colour becomes the accent, so the theme shows both
                accent_hex = hexes[1] if len(hexes) > 1 else hexes[0]
                break
        
        # Inject custom dark theme into Home Assistant
        if DATA_THEMES in hass.data:
            hass.data[DATA_THEMES]["Tasman Bridge"] = {
                # Brand Colors
                "primary-color": active_hex,
                "accent-color": accent_hex,
                
                # Backgrounds
                "primary-background-color": "#111111",
                "card-background-color": "#1c1c1c",
                
                # Text Colors
                "primary-text-color": "#FFFFFF",
                "secondary-text-color": "#b3b3b3",
                "text-primary-color": "#FFFFFF",
                
                # Header
                "app-header-background-color": "#1c1c1c",
                "app-header-text-color": "#FFFFFF",
                
                # Sidebar
                "sidebar-background-color": "#111111",
                "sidebar-text-color": "#FFFFFF",
                "sidebar-selected-background-color": "#2c2c2c",
                "sidebar-selected-text-color": active_hex,
                
                # Icons (Fixing the blue/grey default mdi icons)
                "state-icon-color": active_hex,
                "state-icon-active-color": active_hex,
                "paper-item-icon-color": active_hex,
                "paper-item-icon-active-color": active_hex,
                
                # Inputs and Dropdowns
                "input-fill-color": "#2c2c2c",
                "input-dropdown-menu-background-color": "#1c1c1c",
                "input-dropdown-menu-text-color": "#FFFFFF",
                "input-label-outline-color": "#333333",
                "input-text-color": "#FFFFFF",
                "mdc-theme-surface": "#1c1c1c",
                "mdc-theme-on-surface": "#FFFFFF",
                "mdc-theme-primary": active_hex,
                
                # Misc
                "divider-color": "#333333",
            }
            hass.bus.async_fire("themes_updated")

    # Update theme immediately on boot and every time coordinator fetches
    entry.async_on_unload(coordinator.async_add_listener(update_theme_and_state))
    update_theme_and_state()

    # Schedule targeted refresh times
    # 11:30 AM: Scrape latest data from government website
    async def fetch_latest(*args):
        await coordinator.async_request_refresh()
    # Tracked via async_on_unload so reloads replace these timers rather than
    # stacking a fresh pair on top of the old ones.
    entry.async_on_unload(
        async_track_time_change(hass, fetch_latest, hour=11, minute=30, second=0)
    )

    # 12:00 PM: Force refresh to trigger the midday state & theme rollover
    entry.async_on_unload(
        async_track_time_change(hass, fetch_latest, hour=12, minute=0, second=1)
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok