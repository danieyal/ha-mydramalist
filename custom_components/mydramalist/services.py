from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from mdl import MDLAuthError, MDLError, MDLNotFoundError, MDLSyncError
from mdl.models.auth import UserProfileResponse
from mdl.models.titles import Movie, MovieStatusType

from .const import (
    CATEGORIES,
    CATEGORY_STATUSES,
    CONF_CALENDAR_CATEGORIES,
    DEFAULT_CALENDAR_CATEGORIES,
    DOMAIN,
)
from .data import MyDramaListConfigEntry, normalize_item, normalize_title, title_url
from .entity import tracked_airings

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH = "refresh"
SERVICE_SEARCH = "search"
SERVICE_GET_DRAMA = "get_drama"
SERVICE_GET_RECOMMENDATIONS = "get_recommendations"
SERVICE_GET_TITLES = "get_titles"
SERVICE_GET_AIRING_SCHEDULE = "get_airing_schedule"
SERVICE_UPDATE_ENTRY = "update_entry"
SERVICE_MARK_EPISODE_WATCHED = "mark_episode_watched"
SERVICE_REMOVE_ENTRY = "remove_entry"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_QUERY = "query"
ATTR_TITLE_ID = "title_id"
ATTR_FEED = "feed"
ATTR_ONLY_TRACKED = "only_tracked"
ATTR_STATUS = "status"
ATTR_EPISODE_SEEN = "episode_seen"
ATTR_SCORE = "score"
ATTR_DATE_START = "date_start"
ATTR_DATE_FINISH = "date_finish"
ATTR_TIMES_REWATCHED = "times_rewatched"
ATTR_NOTE = "note"
ATTR_EPISODES = "episodes"
ATTR_COMPLETE = "complete_when_finished"

# get_titles feed -> ExploreResource method.
FEEDS = ("trending", "top_airing", "upcoming", "currently_watching", "top_movies")

_STATUS_CATEGORIES = {status: category for category, status in CATEGORY_STATUSES.items()}

_TITLE_ID_RE = re.compile(r"\d+")

_ENTRY_SCHEMA = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
_TITLE_SCHEMA = {**_ENTRY_SCHEMA, vol.Required(ATTR_TITLE_ID): vol.Any(cv.string, cv.positive_int)}

SCHEMAS: dict[str, vol.Schema] = {
    SERVICE_REFRESH: vol.Schema(_ENTRY_SCHEMA),
    SERVICE_SEARCH: vol.Schema({**_ENTRY_SCHEMA, vol.Required(ATTR_QUERY): cv.string}),
    SERVICE_GET_DRAMA: vol.Schema(_TITLE_SCHEMA),
    SERVICE_GET_RECOMMENDATIONS: vol.Schema(_TITLE_SCHEMA),
    SERVICE_GET_TITLES: vol.Schema({**_ENTRY_SCHEMA, vol.Required(ATTR_FEED): vol.In(FEEDS)}),
    SERVICE_GET_AIRING_SCHEDULE: vol.Schema(
        {**_ENTRY_SCHEMA, vol.Optional(ATTR_ONLY_TRACKED, default=True): cv.boolean}
    ),
    SERVICE_UPDATE_ENTRY: vol.Schema(
        {
            **_TITLE_SCHEMA,
            vol.Optional(ATTR_STATUS): vol.In(CATEGORIES),
            vol.Optional(ATTR_EPISODE_SEEN): cv.positive_int,
            vol.Optional(ATTR_SCORE): vol.All(vol.Coerce(float), vol.Range(min=0, max=10)),
            vol.Optional(ATTR_DATE_START): cv.date,
            vol.Optional(ATTR_DATE_FINISH): cv.date,
            vol.Optional(ATTR_TIMES_REWATCHED): cv.positive_int,
            vol.Optional(ATTR_NOTE): cv.string,
        }
    ),
    SERVICE_MARK_EPISODE_WATCHED: vol.Schema(
        {
            **_TITLE_SCHEMA,
            vol.Optional(ATTR_EPISODES, default=1): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Optional(ATTR_COMPLETE, default=True): cv.boolean,
        }
    ),
    SERVICE_REMOVE_ENTRY: vol.Schema(_TITLE_SCHEMA),
}


def parse_title_id(value: Any) -> int:
    """Accept an id (18452), a slug (18452-goblin) or a mydramalist.com URL."""
    text = str(value).strip()
    if "://" in text:
        text = urlparse(text).path
    text = text.strip("/").split("/", 1)[0]
    if (match := _TITLE_ID_RE.match(text)) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_title_id",
            translation_placeholders={"title_id": str(value)},
        )
    return int(match.group())


def _person_slug(person: UserProfileResponse) -> str | None:
    # People search sends a site path ("/people/440-gong-yoo") instead of a slug.
    if person.slug:
        return person.slug
    return person.url.rstrip("/").rsplit("/", 1)[-1] if person.url else None


def _get_entry(hass: HomeAssistant, call: ServiceCall) -> MyDramaListConfigEntry:
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_loaded"
            )
        return entry
    entries: list[MyDramaListConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    return entries[0]


@contextmanager
def _api_errors() -> Iterator[None]:
    """Report MyDramaList failures as Home Assistant errors."""
    try:
        yield
    except MDLSyncError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="sync_rejected",
            translation_placeholders={"reason": str(err)},
        ) from err
    except MDLNotFoundError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="title_not_found"
        ) from err
    except MDLAuthError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="auth_error"
        ) from err
    except MDLError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="api_error",
            translation_placeholders={"error": str(err)},
        ) from err
    except ValueError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_request",
            translation_placeholders={"error": str(err)},
        ) from err


def _entry_response(movie: Movie) -> dict[str, Any]:
    status = movie.status
    return {
        **normalize_item(movie),
        "status": _STATUS_CATEGORIES.get(status) if status else None,
    }


def async_setup_services(hass: HomeAssistant) -> None:
    async def handle_refresh(call: ServiceCall) -> None:
        if call.data.get(ATTR_CONFIG_ENTRY_ID):
            entries = [_get_entry(hass, call)]
        else:
            entries = hass.config_entries.async_loaded_entries(DOMAIN)
        for entry in entries:
            await entry.runtime_data.coordinator.async_request_refresh()
            await entry.runtime_data.calendar.async_request_refresh()

    async def handle_search(call: ServiceCall) -> dict[str, Any]:
        client = _get_entry(hass, call).runtime_data.client
        query = call.data[ATTR_QUERY]
        with _api_errors():
            titles = await client.search.titles(query)
            people = await client.search.people(query)
        return {
            "dramas": [normalize_title(t) for t in titles],
            "people": [
                {
                    "id": p.id,
                    "slug": _person_slug(p),
                    "name": p.name,
                    "nationality": p.nationality,
                    "thumb": p.thumbnail,
                }
                for p in people
            ],
        }

    async def handle_get_drama(call: ServiceCall) -> dict[str, Any]:
        title_id = parse_title_id(call.data[ATTR_TITLE_ID])
        client = _get_entry(hass, call).runtime_data.client
        with _api_errors():
            title = await client.titles.get_title(title_id)
            credits = await client.titles.get_credits(title_id)
            progress = await client.watchlist.get_progress(title_id)
        link = title_url(title.id, title.permalink)
        return {
            "id": title.id,
            "title": title.title,
            "original_title": title.original_title,
            "year": title.year,
            "rating": title.rating,
            "poster": title.images.poster if title.images else None,
            "thumb": title.images.thumb if title.images else None,
            "synopsis": title.synopsis,
            "link": link,
            "url": link,
            "type": title.type,
            "country": title.country,
            "episodes": title.episodes,
            "runtime": title.runtime,
            "aired_start": title.aired_start,
            "aired_end": title.aired_end,
            "status": title.status,
            "certification": title.certification,
            "ranked": title.ranked,
            "popularity": title.popularity,
            "watchers": title.watchers,
            "votes": title.votes,
            "genres": [g.name for g in title.genres or []],
            "tags": [t.name for t in title.tags or []],
            "alt_titles": [a.name for a in title.alt_titles or []],
            "casts": [
                {
                    "id": c.id,
                    "name": c.name,
                    "character_name": c.character_name,
                    "role": c.role,
                    "thumb": c.images.thumb if c.images else None,
                }
                for c in credits.cast or []
            ],
            # The signed-in user's entry, or None when the title is on no list.
            "my_entry": _entry_response(progress) if progress.list_id else None,
        }

    async def handle_get_recommendations(call: ServiceCall) -> dict[str, Any]:
        title_id = parse_title_id(call.data[ATTR_TITLE_ID])
        client = _get_entry(hass, call).runtime_data.client
        with _api_errors():
            titles = await client.titles.get_recommendations(title_id)
        return {"titles": [normalize_title(t) for t in titles]}

    async def handle_get_titles(call: ServiceCall) -> dict[str, Any]:
        client = _get_entry(hass, call).runtime_data.client
        with _api_errors():
            titles = await getattr(client.explore, call.data[ATTR_FEED])()
        return {"titles": [normalize_title(t) for t in titles]}

    async def handle_get_airing_schedule(call: ServiceCall) -> dict[str, Any]:
        entry = _get_entry(hass, call)
        runtime = entry.runtime_data
        airings = runtime.calendar.data or []
        if call.data[ATTR_ONLY_TRACKED]:
            categories = entry.options.get(CONF_CALENDAR_CATEGORIES, DEFAULT_CALENDAR_CATEGORIES)
            pairs = tracked_airings(airings, runtime.coordinator.data, categories)
        else:
            known = runtime.coordinator.data.title_categories()
            pairs = [(airing, known.get(airing.title_id)) for airing in airings]
        now = dt_util.utcnow()
        return {
            "airings": [
                {
                    "title": airing.title,
                    "title_id": airing.title_id,
                    "episode": airing.episode,
                    "start": airing.start.isoformat(),
                    "end": airing.end.isoformat(),
                    "aired": airing.start <= now,
                    "category": category,
                    "type": airing.type,
                    "country": airing.country,
                    "genres": airing.genres,
                    "url": airing.url,
                    "thumb": airing.thumb,
                }
                for airing, category in pairs
            ]
        }

    async def handle_update_entry(call: ServiceCall) -> dict[str, Any]:
        title_id = parse_title_id(call.data[ATTR_TITLE_ID])
        runtime = _get_entry(hass, call).runtime_data
        status = call.data.get(ATTR_STATUS)
        with _api_errors():
            movie = await runtime.client.watchlist.update(
                title_id,
                status=CATEGORY_STATUSES[status] if status else None,
                episode_seen=call.data.get(ATTR_EPISODE_SEEN),
                rating=call.data.get(ATTR_SCORE),
                date_start=call.data.get(ATTR_DATE_START),
                date_finish=call.data.get(ATTR_DATE_FINISH),
                times_rewatched=call.data.get(ATTR_TIMES_REWATCHED),
                note=call.data.get(ATTR_NOTE),
            )
        await runtime.coordinator.async_request_refresh()
        return {"entry": _entry_response(movie)}

    async def handle_mark_episode_watched(call: ServiceCall) -> dict[str, Any]:
        title_id = parse_title_id(call.data[ATTR_TITLE_ID])
        runtime = _get_entry(hass, call).runtime_data
        client = runtime.client
        with _api_errors():
            current = await client.watchlist.get_progress(title_id)
            if current.status is MovieStatusType.COMPLETED:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="already_completed"
                )
            total = current.title.episodes if current.title else None
            seen = (current.episode_seen or 0) + call.data[ATTR_EPISODES]
            if total:
                seen = min(seen, total)
            if total and seen >= total and call.data[ATTR_COMPLETE]:
                status = MovieStatusType.COMPLETED
            else:
                # Watching an episode puts a planned, paused or dropped title back on
                # Watching.
                status = MovieStatusType.WATCHING
            movie = await client.watchlist.update(
                title_id, status=status, episode_seen=seen, current=current
            )
        await runtime.coordinator.async_request_refresh()
        return {"entry": _entry_response(movie)}

    async def handle_remove_entry(call: ServiceCall) -> dict[str, Any]:
        title_id = parse_title_id(call.data[ATTR_TITLE_ID])
        runtime = _get_entry(hass, call).runtime_data
        with _api_errors():
            result = await runtime.client.watchlist.remove([title_id])
        deleted = result.deleted.get("titles") if isinstance(result.deleted, dict) else None
        if not deleted:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_on_list"
            )
        await runtime.coordinator.async_request_refresh()
        return {"removed": deleted}

    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, handle_refresh, schema=SCHEMAS[SERVICE_REFRESH]
    )
    for service, handler, response in (
        (SERVICE_SEARCH, handle_search, SupportsResponse.ONLY),
        (SERVICE_GET_DRAMA, handle_get_drama, SupportsResponse.ONLY),
        (SERVICE_GET_RECOMMENDATIONS, handle_get_recommendations, SupportsResponse.ONLY),
        (SERVICE_GET_TITLES, handle_get_titles, SupportsResponse.ONLY),
        (SERVICE_GET_AIRING_SCHEDULE, handle_get_airing_schedule, SupportsResponse.ONLY),
        (SERVICE_UPDATE_ENTRY, handle_update_entry, SupportsResponse.OPTIONAL),
        (SERVICE_MARK_EPISODE_WATCHED, handle_mark_episode_watched, SupportsResponse.OPTIONAL),
        (SERVICE_REMOVE_ENTRY, handle_remove_entry, SupportsResponse.OPTIONAL),
    ):
        hass.services.async_register(
            DOMAIN, service, handler, schema=SCHEMAS[service], supports_response=response
        )
