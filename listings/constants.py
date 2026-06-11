from django.utils.translation import gettext_lazy as _

# Ported unchanged from legacy backend/advertisements/constants.py,
# except STATUS_CHOICES reduced per rebuild spec §3.1.

# Database values (snake_case) and their display names
CATEGORY_CHOICES = [
  ("photography_videography", _("Photography & Videography")),
  ("sports_outdoor", _("Sports & Outdoor")),
  ("camping_hiking", _("Camping & Hiking")),
  ("travel_luggage", _("Travel & Luggage")),
  ("event_party", _("Event & Party")),
  ("fashion_accessories", _("Fashion & Accessories")),
  ("electronics", _("Electronics")),
  ("tools_equipment", _("Tools & Equipment")),
  ("musical_instruments", _("Musical Instruments")),
  ("other", _("Other")),
]

# Product types mapped to their categories (using database values)
PRODUCT_TYPE_CHOICES = [
  # Photography & Videography
  ("camera", "photography_videography"),
  ("lens", "photography_videography"),
  ("gimbal", "photography_videography"),
  ("tripod", "photography_videography"),
  ("drone", "photography_videography"),
  ("lighting", "photography_videography"),
  ("video_camera", "photography_videography"),
  ("microphone", "photography_videography"),
  ("stabilizer", "photography_videography"),
  ("slider", "photography_videography"),
  ("reflector", "photography_videography"),
  ("monitor", "photography_videography"),
  ("memory_card", "photography_videography"),
  ("battery", "photography_videography"),
  ("charger", "photography_videography"),
  ("light_stand", "photography_videography"),
  ("softbox", "photography_videography"),
  ("backdrop", "photography_videography"),
  # Sports & Outdoor
  ("cricket_bat", "sports_outdoor"),
  ("football", "sports_outdoor"),
  ("badminton_racket", "sports_outdoor"),
  ("helmet", "sports_outdoor"),
  ("sports_gear", "sports_outdoor"),
  ("running_shoes", "sports_outdoor"),
  ("bicycle", "sports_outdoor"),
  ("skipping_rope", "sports_outdoor"),
  # Camping & Hiking
  ("backpack", "camping_hiking"),
  ("headlamp", "camping_hiking"),
  ("gas_can", "camping_hiking"),
  ("raincover", "camping_hiking"),
  ("poncho", "camping_hiking"),
  ("jacket", "camping_hiking"),
  ("sleeping_bag", "camping_hiking"),
  ("tent", "camping_hiking"),
  ("stove", "camping_hiking"),
  ("water_bottle", "camping_hiking"),
  ("hiking_pole", "camping_hiking"),
  ("camping_chair", "camping_hiking"),
  # Travel & Luggage
  ("suitcase", "travel_luggage"),
  ("travel_adapter", "travel_luggage"),
  ("power_bank", "travel_luggage"),
  ("travel_bag", "travel_luggage"),
  ("trolley", "travel_luggage"),
  # Event & Party
  ("sound_system", "event_party"),
  ("decorations", "event_party"),
  ("chair", "event_party"),
  ("table", "event_party"),
  ("stage_light", "event_party"),
  ("projector", "event_party"),
  ("tent", "event_party"),
  # Fashion & Accessories
  ("formal_wear", "fashion_accessories"),
  ("jewelry", "fashion_accessories"),
  ("costume", "fashion_accessories"),
  ("watch", "fashion_accessories"),
  ("sunglasses", "fashion_accessories"),
  # Electronics
  ("laptop", "electronics"),
  ("tablet", "electronics"),
  ("smartphone", "electronics"),
  ("projector", "electronics"),
  ("speaker", "electronics"),
  ("tv", "electronics"),
  ("printer", "electronics"),
  ("scanner", "electronics"),
  ("router", "electronics"),
  # Tools & Equipment
  ("power_tools", "tools_equipment"),
  ("hand_tools", "tools_equipment"),
  ("measuring_tape", "tools_equipment"),
  ("drill_machine", "tools_equipment"),
  ("ladder", "tools_equipment"),
  ("cleaning_equipment", "tools_equipment"),
  # Musical Instruments
  ("guitar", "musical_instruments"),
  ("keyboard", "musical_instruments"),
  ("harmonium", "musical_instruments"),
  ("tabla", "musical_instruments"),
  ("microphone", "musical_instruments"),
  ("amplifier", "musical_instruments"),
  ("drum", "musical_instruments"),
  ("violin", "musical_instruments"),
  # Other
  ("other", "other"),
]

# Display names for product types (for UI)
PRODUCT_TYPE_DISPLAY = {
  # Photography & Videography
  "camera": _("Camera"),
  "lens": _("Lens"),
  "gimbal": _("Gimbal"),
  "tripod": _("Tripod"),
  "drone": _("Drone"),
  "lighting": _("Lighting"),
  "video_camera": _("Video Camera"),
  "microphone": _("Microphone"),
  "stabilizer": _("Stabilizer"),
  "slider": _("Slider"),
  "reflector": _("Reflector"),
  "monitor": _("Monitor"),
  "memory_card": _("Memory Card"),
  "battery": _("Battery"),
  "charger": _("Charger"),
  "light_stand": _("Light Stand"),
  "softbox": _("Softbox"),
  "backdrop": _("Backdrop"),
  # Sports & Outdoor
  "cricket_bat": _("Cricket Bat"),
  "football": _("Football"),
  "badminton_racket": _("Badminton Racket"),
  "helmet": _("Helmet"),
  "sports_gear": _("Sports Gear"),
  "running_shoes": _("Running Shoes"),
  "bicycle": _("Bicycle"),
  "skipping_rope": _("Skipping Rope"),
  # Camping & Hiking
  "backpack": _("Backpack"),
  "headlamp": _("Headlamp"),
  "gas_can": _("Gas Can"),
  "raincover": _("Raincover"),
  "poncho": _("Poncho"),
  "jacket": _("Jacket"),
  "sleeping_bag": _("Sleeping Bag"),
  "tent": _("Tent"),
  "stove": _("Stove"),
  "water_bottle": _("Water Bottle"),
  "hiking_pole": _("Hiking Pole"),
  "camping_chair": _("Camping Chair"),
  # Travel & Luggage
  "suitcase": _("Suitcase"),
  "travel_adapter": _("Travel Adapter"),
  "power_bank": _("Power Bank"),
  "travel_bag": _("Travel Bag"),
  "trolley": _("Trolley"),
  # Event & Party
  "sound_system": _("Sound System"),
  "decorations": _("Decorations"),
  "chair": _("Chair"),
  "table": _("Table"),
  "stage_light": _("Stage Light"),
  "projector": _("Projector"),
  # Fashion & Accessories
  "formal_wear": _("Formal Wear"),
  "jewelry": _("Jewelry"),
  "costume": _("Costume"),
  "watch": _("Watch"),
  "sunglasses": _("Sunglasses"),
  # Electronics
  "laptop": _("Laptop"),
  "tablet": _("Tablet"),
  "smartphone": _("Smartphone"),
  "speaker": _("Speaker"),
  "tv": _("TV"),
  "printer": _("Printer"),
  "scanner": _("Scanner"),
  "router": _("Router"),
  # Tools & Equipment
  "power_tools": _("Power Tools"),
  "hand_tools": _("Hand Tools"),
  "measuring_tape": _("Measuring Tape"),
  "drill_machine": _("Drill Machine"),
  "ladder": _("Ladder"),
  "cleaning_equipment": _("Cleaning Equipment"),
  # Musical Instruments
  "guitar": _("Guitar"),
  "keyboard": _("Keyboard"),
  "harmonium": _("Harmonium"),
  "tabla": _("Tabla"),
  "amplifier": _("Amplifier"),
  "drum": _("Drum"),
  "violin": _("Violin"),
  # Other
  "other": _("Other"),
}

DURATION_UNITS = [
  ("day", _("Per Day")),
  ("week", _("Per Week")),
  ("month", _("Per Month")),
]

OWNERSHIP_HISTORY_CHOICES = [
  ("firsthand", _("First Hand")),
  ("secondhand", _("Second Hand")),
]

# Reduced per spec §3.1: 'rented' derived from rentals, 'maintenance' removed.
STATUS_CHOICES = [
  ("draft", _("Draft")),
  ("active", _("Active - Available for Rent")),
  ("suspended", _("Suspended - Listing Disabled")),
]
