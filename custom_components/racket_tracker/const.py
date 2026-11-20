"""Constants for the Strung integration."""

from __future__ import annotations

DOMAIN = "racket_tracker"
STORAGE_VERSION = 1

# Racket (config entry) options
CONF_BRAND = "brand"
CONF_MODEL = "model"
CONF_HEAD_SIZE = "head_size"
CONF_STRING_PATTERN = "string_pattern"
CONF_TENSION_UNIT = "tension_unit"

# The racket's usual setup (option section), used by repeat_restring
CONF_SETUP = "setup"

# The strings on the racket now (add/options form section, not stored as an option)
CONF_CURRENT = "current"

TENSION_UNIT_LBS = "lbs"
TENSION_UNIT_KG = "kg"
TENSION_UNITS = [TENSION_UNIT_LBS, TENSION_UNIT_KG]

# Restring record fields
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_RESTRING_ID = "restring_id"
ATTR_DATE = "date"
ATTR_MAIN_STRING = "main_string"
ATTR_CROSS_STRING = "cross_string"
ATTR_MAIN_TENSION = "main_tension"
ATTR_CROSS_TENSION = "cross_tension"
ATTR_COST = "cost"
ATTR_STRINGER = "stringer"
ATTR_RATING = "rating"
ATTR_NOTES = "notes"
ATTR_IMAGE = "image"
ATTR_IMAGE_URL = "image_url"
ATTR_REMOVE_IMAGE = "remove_image"
# The date this string bed broke (None if it didn't)
ATTR_BROKEN_DATE = "broken_date"
ATTR_BROKEN = "broken"
# Play session fields (log_play)
ATTR_SESSION_ID = "session_id"
ATTR_HOURS = "hours"
ATTR_SESSION_TYPE = "session_type"
ATTR_SURFACE = "surface"
# Calibration fields
ATTR_TOOL = "tool"

SESSION_TYPES = ["singles_match", "doubles_match", "practice", "ball_machine"]
SURFACES = ["hard", "clay", "grass", "indoor"]

EDITABLE_FIELDS = (
    ATTR_DATE,
    ATTR_MAIN_STRING,
    ATTR_CROSS_STRING,
    ATTR_MAIN_TENSION,
    ATTR_CROSS_TENSION,
    ATTR_COST,
    ATTR_STRINGER,
    ATTR_RATING,
    ATTR_NOTES,
    ATTR_BROKEN_DATE,
)

# Fields a repeated restring copies from the usual setup or a past restring
SETUP_FIELDS = (
    ATTR_MAIN_STRING,
    ATTR_MAIN_TENSION,
    ATTR_CROSS_STRING,
    ATTR_CROSS_TENSION,
    ATTR_STRINGER,
    ATTR_COST,
)

# Services
SERVICE_ADD_RESTRING = "add_restring"
SERVICE_UPDATE_RESTRING = "update_restring"
SERVICE_DELETE_RESTRING = "delete_restring"
SERVICE_GET_HISTORY = "get_history"
SERVICE_REPEAT_RESTRING = "repeat_restring"
SERVICE_CALIBRATE_TENSION = "calibrate_tension"
SERVICE_EXPORT_HISTORY = "export_history"
SERVICE_IMPORT_HISTORY = "import_history"
SERVICE_LOG_PLAY = "log_play"
SERVICE_UPDATE_PLAY = "update_play"
SERVICE_DELETE_PLAY = "delete_play"
SERVICE_GET_BAG_SUMMARY = "get_bag_summary"
SERVICE_EXPORT_BACKUP = "export_backup"
SERVICE_IMPORT_BACKUP = "import_backup"

# Events
EVENT_RESTRUNG = f"{DOMAIN}_restrung"
