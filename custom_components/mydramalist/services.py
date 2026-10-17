import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError

from mdl import AsyncMDLClient
from mdl.models.auth import UserProfileResponse

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH = "refresh"
SERVICE_SEARCH = "search"
SERVICE_GET_DRAMA = "get_drama"

# Accepts a bare id ("18452") or a MyDramaList slug ("18452-goblin").
_TITLE_ID_RE = re.compile(r"\d+")


def _person_slug(person: UserProfileResponse) -> str | None:
    # People search sends a site path ("/people/440-gong-yoo") instead of a slug.
    if person.slug:
        return person.slug
    return person.url.rstrip("/").rsplit("/", 1)[-1] if person.url else None


def _get_client(hass: HomeAssistant) -> AsyncMDLClient | None:
    for entry_data in hass.data[DOMAIN].values():
        return entry_data["client"]
    return None


def async_setup_services(hass: HomeAssistant) -> None:
    async def handle_refresh(call: ServiceCall) -> None:
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data["coordinator"]
            await coordinator.async_request_refresh()

    async def handle_search(call: ServiceCall) -> dict[str, Any]:
        query = call.data["query"]

        client = _get_client(hass)
        if client is None:
            _LOGGER.warning("Search called with no configured MyDramaList entries")
            return {"dramas": [], "people": []}

        titles = await client.search.titles(query)
        people = await client.search.people(query)

        return {
            "dramas": [
                {
                    "id": t.id,
                    "title": t.title,
                    "original_title": t.original_title,
                    "year": t.year,
                    "type": t.type,
                    "country": t.country,
                    "episodes": t.episodes,
                    "rating": t.rating,
                    "rank": t.rank,
                    "thumb": t.images.thumb if t.images else None,
                }
                for t in titles
            ],
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
        raw_id = str(call.data["title_id"]).strip()
        if (match := _TITLE_ID_RE.match(raw_id)) is None:
            raise ServiceValidationError(
                f"'{raw_id}' is not a MyDramaList title id or slug"
            )
        title_id = int(match.group())

        client = _get_client(hass)
        if client is None:
            _LOGGER.warning("get_drama called with no configured MyDramaList entries")
            return {}

        title = await client.titles.get_title(title_id)
        credits = await client.titles.get_credits(title_id)

        return {
            "id": title.id,
            "title": title.title,
            "original_title": title.original_title,
            "year": title.year,
            "rating": title.rating,
            "poster": title.images.poster if title.images else None,
            "synopsis": title.synopsis,
            "link": title.permalink,
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
        }

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh)
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH,
        handle_search,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_DRAMA,
        handle_get_drama,
        supports_response=SupportsResponse.ONLY,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
    hass.services.async_remove(DOMAIN, SERVICE_SEARCH)
    hass.services.async_remove(DOMAIN, SERVICE_GET_DRAMA)
