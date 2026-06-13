from datetime import timedelta

DOMAIN = "mydramalist"
NAME = "MyDramaList"
DEFAULT_API_URL = "https://kuryana.tbdh.app"

CONF_USER_ID = "user_id"
CONF_API_URL = "api_url"

DEFAULT_UPDATE_INTERVAL = timedelta(hours=1)

PLATFORMS = ["sensor"]

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
