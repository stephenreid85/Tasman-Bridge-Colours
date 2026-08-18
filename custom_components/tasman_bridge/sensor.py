"""Sensor platform for Tasman Bridge."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN, DEFAULT_COLOR

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    # Create Date, Colour, and Purpose sensors for the next 3 events, passing entry_id
    for i in range(3):
        entities.append(TasmanBridgeSensor(coordinator, entry.entry_id, i, "date"))
        entities.append(TasmanBridgeSensor(coordinator, entry.entry_id, i, "colour"))
        entities.append(TasmanBridgeSensor(coordinator, entry.entry_id, i, "purpose"))
        
    async_add_entities(entities)

class TasmanBridgeSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Tasman Bridge sensor."""

    def __init__(self, coordinator, entry_id, index, field):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._index = index
        self._field = field
        
        event_num = index + 1
        field_cap = field.capitalize()
        self._attr_name = f"Tasman Bridge Event {event_num} {field_cap}"
        self._attr_unique_id = f"tasman_bridge_event_{event_num}_{field}"
        self._attr_icon = self._get_icon()

    @property
    def device_info(self) -> DeviceInfo:
        """Link this entity to the Tasman Bridge device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Tasman Bridge",
            manufacturer="Tasmanian Government",
            model="Lighting Schedule"
        )

    def _get_icon(self):
        if self._field == "date": return "mdi:calendar"
        if self._field == "colour": return "mdi:palette"
        return "mdi:bridge"

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return "Unknown"

        current_time = dt_util.now()
        
        # Filter out past events (events that ended before right now)
        upcoming_events = [e for e in self.coordinator.data if e["active_end"] > current_time]

        if self._index < len(upcoming_events):
            event = upcoming_events[self._index]
            if self._field == "date":
                return event["date_str"]
            if self._field == "colour":
                return event["color_name"]
            if self._field == "purpose":
                return event["purpose"]
        
        # Fallback if no event is scheduled for this slot
        if self._field == "colour":
            return DEFAULT_COLOR.title()
        return "None Scheduled"

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        if self._field != "colour" or not self.coordinator.data:
            return {}

        current_time = dt_util.now()
        upcoming_events = [e for e in self.coordinator.data if e["active_end"] > current_time]
        if self._index >= len(upcoming_events):
            return {}

        event = upcoming_events[self._index]
        return {
            # hex_value stays the primary colour so existing cards keep working
            "hex_value": event["color_hex"],
            "hex_values": event["color_hexes"],
            "colour_names": event["color_names"],
            "is_multi_colour": len(event["color_hexes"]) > 1,
        }
