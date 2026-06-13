import logging
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall

from kuryana import AsyncKuryana

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH = "refresh"
SERVICE_SEARCH = "search"
SERVICE_GET_DRAMA = "get_drama"


def async_setup_services(hass: HomeAssistant) -> None:
    async def handle_refresh(call: ServiceCall) -> None:
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data["coordinator"]
            await coordinator.async_request_refresh()

    async def handle_search(call: ServiceCall) -> dict[str, Any]:
        query = call.data["query"]

        result = None
        for entry_data in hass.data[DOMAIN].values():
            client: AsyncKuryana = entry_data["client"]
            result = await client.search(query)
            break

        if result is None:
            _LOGGER.warning("Search called with no configured MyDramaList entries")
            return {"dramas": [], "people": []}

        return {
            "dramas": [
                {
                    "slug": d.slug,
                    "title": d.title,
                    "year": d.year,
                    "type": d.type,
                    "mdl_id": d.mdl_id,
                    "thumb": d.thumb,
                    "ranking": d.ranking,
                    "series": d.series,
                }
                for d in result.results.dramas
            ],
            "people": [
                {
                    "slug": p.slug,
                    "name": p.name,
                    "nationality": p.nationality,
                    "thumb": p.thumb,
                }
                for p in result.results.people
            ],
        }

    async def handle_get_drama(call: ServiceCall) -> dict[str, Any]:
        slug = call.data["slug"]

        result = None
        for entry_data in hass.data[DOMAIN].values():
            client: AsyncKuryana = entry_data["client"]
            result = await client.get_drama(slug)
            break

        if result is None:
            _LOGGER.warning("get_drama called with no configured MyDramaList entries")
            return {}

        data = result.data
        return {
            "title": data.title,
            "complete_title": data.complete_title,
            "sub_title": data.sub_title,
            "year": data.year,
            "rating": data.rating,
            "poster": data.poster,
            "synopsis": data.synopsis,
            "link": data.link,
            "casts": [
                {
                    "name": c.name,
                    "slug": c.slug,
                    "profile_image": c.profile_image,
                    "link": c.link,
                }
                for c in data.casts
            ],
            "details": {
                "country": data.details.country,
                "type": data.details.type,
                "episodes": data.details.episodes,
                "aired": data.details.aired,
                "original_network": data.details.original_network,
                "duration": data.details.duration,
                "score": data.details.score,
                "ranked": data.details.ranked,
                "popularity": data.details.popularity,
                "content_rating": data.details.content_rating,
                "watchers": data.details.watchers,
                "favorites": data.details.favorites,
            },
            "others": {
                "related_content": data.others.related_content,
                "native_title": data.others.native_title,
                "also_known_as": data.others.also_known_as,
                "genres": data.others.genres,
                "tags": data.others.tags,
            },
            "scrape_date": result.scrape_date.isoformat(),
        }

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh)
    hass.services.async_register(DOMAIN, SERVICE_SEARCH, handle_search)
    hass.services.async_register(DOMAIN, SERVICE_GET_DRAMA, handle_get_drama)


def async_unload_services(hass: HomeAssistant) -> None:
    hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
    hass.services.async_remove(DOMAIN, SERVICE_SEARCH)
    hass.services.async_remove(DOMAIN, SERVICE_GET_DRAMA)
