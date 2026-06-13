from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from kuryana.types.user import (
    UserData,
    UserDataList,
    UserDataListGroup,
    UserDataListItem,
    UserDataStats,
    UserQuery,
)


@pytest.fixture
def mock_kuryana_client() -> Generator[MagicMock, None, None]:
    with patch("kuryana.AsyncKuryana", autospec=True) as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_user_query() -> UserQuery:
    return UserQuery(
        slug_query="testuser",
        data=UserData(
            link="https://mydramalist.com/dramalist/testuser",
            list=UserDataList(
                Completed=UserDataListGroup(
                    items=[
                        UserDataListItem(
                            name="Goblin",
                            id="goblin",
                            score="10",
                            episode_seen="16",
                            episode_total="16",
                        ),
                        UserDataListItem(
                            name="Descendants of the Sun",
                            id="descendants-of-the-sun",
                            score="9",
                            episode_seen="16",
                            episode_total="16",
                        ),
                    ],
                    stats=UserDataStats(
                        Dramas="2",
                        **{"TV Shows": "2"},
                        Episodes="32",
                        Movies="0",
                        Days="2.5",
                    ),
                ),
                Plan_to_Watch=UserDataListGroup(
                    items=[
                        UserDataListItem(
                            name="Vincenzo",
                            id="vincenzo",
                            score="0",
                            episode_seen="0",
                            episode_total="20",
                        ),
                    ],
                    stats=UserDataStats(
                        Dramas="1",
                        **{"TV Shows": "1"},
                        Episodes="20",
                        Movies="0",
                        Days="1.3",
                    ),
                ),
                On_hold=UserDataListGroup(
                    items=[],
                    stats=UserDataStats(
                        Dramas="0",
                        **{"TV Shows": "0"},
                        Episodes="0",
                        Movies="0",
                        Days="0",
                    ),
                ),
                Dropped=UserDataListGroup(
                    items=[
                        UserDataListItem(
                            name="The Heirs",
                            id="the-heirs",
                            score="4",
                            episode_seen="6",
                            episode_total="20",
                        ),
                    ],
                    stats=UserDataStats(
                        Dramas="1",
                        **{"TV Shows": "1"},
                        Episodes="6",
                        Movies="0",
                        Days="0.4",
                    ),
                ),
            ),
        ),
        scrape_date=datetime(2025, 6, 13, 12, 0, 0),
    )
