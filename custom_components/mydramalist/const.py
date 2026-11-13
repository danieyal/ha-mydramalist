from datetime import timedelta

from mdl.models.titles import MovieStatusType

DOMAIN = "mydramalist"
NAME = "MyDramaList"
VERSION = "0.3.0"

WEBSITE_URL = "https://mydramalist.com"

CONF_DEVICE_ID = "device_id"

# Version 1 entries were configured against the Kuryana scraper.
CONF_USER_ID = "user_id"

CONF_UPDATE_INTERVAL = "update_interval"
CONF_CALENDAR_CATEGORIES = "calendar_categories"

DEFAULT_UPDATE_INTERVAL = 60  # minutes
MIN_UPDATE_INTERVAL = 15
MAX_UPDATE_INTERVAL = 1440

# The airing schedule only covers a week and changes slowly.
CALENDAR_UPDATE_INTERVAL = timedelta(hours=3)
# Airings older than this are dropped from the calendar's cache.
CALENDAR_RETENTION = timedelta(days=14)
# Used as an episode's length when the schedule gives no duration.
DEFAULT_EPISODE_DURATION = timedelta(hours=1)

PLATFORMS = ["calendar", "sensor"]

CATEGORY_WATCHING = "watching"
CATEGORY_COMPLETED = "completed"
CATEGORY_PLAN_TO_WATCH = "plan_to_watch"
CATEGORY_ON_HOLD = "on_hold"
CATEGORY_DROPPED = "dropped"

CATEGORIES = [
    CATEGORY_WATCHING,
    CATEGORY_COMPLETED,
    CATEGORY_PLAN_TO_WATCH,
    CATEGORY_ON_HOLD,
    CATEGORY_DROPPED,
]

CATEGORY_STATUSES = {
    CATEGORY_WATCHING: MovieStatusType.WATCHING,
    CATEGORY_COMPLETED: MovieStatusType.COMPLETED,
    CATEGORY_PLAN_TO_WATCH: MovieStatusType.PLAN_TO_WATCH,
    CATEGORY_ON_HOLD: MovieStatusType.ON_HOLD,
    CATEGORY_DROPPED: MovieStatusType.DROPPED,
}

DEFAULT_CALENDAR_CATEGORIES = [CATEGORY_WATCHING, CATEGORY_PLAN_TO_WATCH]

# The Lovelace cards bundled in frontend/.
FRONTEND_URL = f"/{DOMAIN}_static"
CARD_FILENAME = "mydramalist-card.js"
