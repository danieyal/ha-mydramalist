"""Normalized MyDramaList data shared by the coordinators, entities and services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry

from mdl.models.misc import Episodes, UserStats
from mdl.models.titles import Movie, MovieTitle

from .const import DEFAULT_EPISODE_DURATION, WEBSITE_URL

if TYPE_CHECKING:
    from mdl import AsyncMDLClient

    from .coordinator import MyDramaListCalendarCoordinator, MyDramaListCoordinator

# The API's placeholders for an unset date.
_UNSET_DATES = ("0000-00-00", "1970-01-01", "0001-01-01")


@dataclass
class MyDramaListRuntimeData:
    client: AsyncMDLClient
    coordinator: MyDramaListCoordinator
    calendar: MyDramaListCalendarCoordinator


type MyDramaListConfigEntry = ConfigEntry[MyDramaListRuntimeData]


@dataclass
class UserData:
    username: str
    display_name: str | None = None
    avatar: str | None = None


@dataclass
class MyDramaListData:
    """One poll of the account: list items per category plus account totals."""

    lists: dict[str, list[dict[str, Any]]]
    user: UserData
    # ``all`` from /sync/last_activities; unchanged means no list changed.
    last_activity: str | None = None
    stats: dict[str, Any] | None = None
    unread: dict[str, int] | None = None

    @property
    def total_count(self) -> int:
        return sum(len(items) for items in self.lists.values())

    def title_categories(self) -> dict[int, str]:
        """Map each title id on the lists to its category."""
        return {
            item["id"]: category
            for category, items in self.lists.items()
            for item in items
            if item["id"] is not None
        }

    def find(self, title_id: int) -> tuple[str, dict[str, Any]] | None:
        for category, items in self.lists.items():
            for item in items:
                if item["id"] == title_id:
                    return category, item
        return None


@dataclass(frozen=True)
class Airing:
    """An episode (or a movie's release) on the airing calendar."""

    uid: str
    title_id: int
    title: str
    episode: int | None
    start: datetime
    end: datetime
    url: str | None
    thumb: str | None = None
    type: str | None = None
    country: str | None = None
    genres: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.episode:
            return f"{self.title} · Episode {self.episode}"
        return self.title


def title_url(title_id: int | None, permalink: str | None = None) -> str | None:
    """A title's page; ``permalink`` is a site path (``/18452-goblin``) or a full URL."""
    if permalink and permalink.startswith(("http://", "https://")):
        return permalink
    if permalink:
        return f"{WEBSITE_URL}/{permalink.lstrip('/')}"
    return f"{WEBSITE_URL}/{title_id}" if title_id else None


def clean_date(value: str | None) -> str | None:
    if not value or value.startswith(_UNSET_DATES):
        return None
    return value


def normalize_title(title: MovieTitle) -> dict[str, Any]:
    """The fields services return for a compact title (search, feeds, recommendations)."""
    return {
        "id": title.id,
        "title": title.title,
        "original_title": title.original_title,
        "year": title.year,
        "type": title.type,
        "country": title.country,
        "episodes": title.episodes,
        "rating": title.rating,
        "rank": title.rank,
        "url": title_url(title.id, title.permalink),
        "thumb": title.images.thumb if title.images else None,
    }


def normalize_item(movie: Movie) -> dict[str, Any]:
    """A list entry as exposed in the category sensors' ``items`` attribute."""
    title = movie.title
    seen = movie.episode_seen or 0
    total = title.episodes if title else None
    return {
        "id": title.id if title else None,
        "name": title.title if title else None,
        "url": title_url(title.id) if title else None,
        "thumb": title.images.thumb if title and title.images else None,
        "year": title.year if title else None,
        "type": title.type if title else None,
        "country": title.country if title else None,
        "score": movie.rating,
        "episode_seen": movie.episode_seen,
        "episode_total": total,
        "progress": round(seen / total * 100) if total else None,
        "date_start": clean_date(movie.date_start),
        "date_finish": clean_date(movie.date_finish),
        "updated_at": movie.updated_at,
    }


def normalize_list(movies: list[Movie]) -> list[dict[str, Any]]:
    # The sync endpoint flags removed entries rather than omitting them.
    return [normalize_item(movie) for movie in movies if not movie.deleted]


def list_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [item["score"] for item in items if item["score"]]
    return {
        "episodes_seen": sum(item["episode_seen"] or 0 for item in items),
        "mean_score": round(sum(scores) / len(scores), 2) if scores else None,
    }


def normalize_stats(stats: UserStats) -> dict[str, Any]:
    shows = stats.total("Shows")
    movies = stats.total("Movie")
    mean = stats.ratings.mean if stats.ratings else None
    return {
        "episodes_watched": shows.watched,
        "movies_watched": movies.watched,
        "minutes_watched": (shows.minutes or 0) + (movies.minutes or 0),
        "mean_score": round(mean, 2) if mean is not None else None,
        "ratings": stats.ratings.total if stats.ratings else None,
        "score_distribution": dict(
            sorted(
                (stats.ratings.distribution or {}).items() if stats.ratings else (),
                key=lambda pair: float(pair[0]),
            )
        ),
        "reviews": stats.reviews,
        "comments": stats.comments,
        "friends": stats.friends,
        "custom_lists": stats.custom_lists,
    }


def airings_from_calendar(calendar: Episodes) -> list[Airing]:
    titles = {rel.id: rel for rel in calendar.relationships or []}
    airings: list[Airing] = []
    for item in calendar.items or []:
        start = item.released_datetime
        rel = titles.get(item.rid)
        if start is None or rel is None or item.rid is None:
            continue
        duration = item.duration
        airings.append(
            Airing(
                uid=str(item.id),
                title_id=int(item.rid),
                title=rel.title or str(item.rid),
                episode=item.episode_number or None,
                start=start,
                end=start + (timedelta(minutes=duration) if duration else DEFAULT_EPISODE_DURATION),
                url=title_url(int(item.rid), item.permalink or rel.url),
                thumb=rel.thumbnail,
                type=rel.type,
                country=rel.country,
                genres=[g for g in str(rel.genres or "").split(",") if g],
            )
        )
    airings.sort(key=lambda airing: (airing.start, airing.title, airing.episode or 0))
    return airings

