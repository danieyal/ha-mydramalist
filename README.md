# ha-mydramalist

Home Assistant custom integration for [MyDramaList](https://mydramalist.com) powered by [mydramalist-client](https://pypi.org/project/mydramalist-client/) ([pymdl](https://github.com/danieyal/pymdl)), an unofficial client for the MyDramaList app API.

Tracks your lists — watching, completed, plan to watch, on hold, dropped — and your watch stats, puts upcoming episodes of your dramas on a calendar, and lets automations and dashboards update your progress.

## Features

- **List sensors** for each list with every title's poster, progress, score and dates
- **Watch stats** — episodes and movies watched, total time watched and mean score, with long-term statistics
- **Episode calendar** and a **next episode** sensor for the titles on your Watching and Plan to Watch lists (configurable)
- **Write actions** — mark episodes watched, change a title's list, score or dates, add and remove titles
- **Discovery actions** — search, title details, recommendations, trending / top airing / upcoming feeds, the week's airing schedule
- **Dashboard cards** — list, upcoming-episodes and stats cards, bundled and loaded automatically, plus a [ready-made dashboard](examples/dashboard.yaml)
- **Unread notifications** sensor
- Config flow with re-authentication, reconfiguration, options and diagnostics

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Search for "MyDramaList" in HACS and install
3. Restart Home Assistant

### Manual

```sh
cd <ha-config>/custom_components
git clone https://github.com/danieyal/ha-mydramalist.git mydramalist
```

Then restart Home Assistant.

## Setup

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **MyDramaList**
3. Enter your MyDramaList username and password

The app API only serves the signed-in user's lists, so the integration tracks the account you sign in with. Your password is stored in the Home Assistant config entry and is redacted from diagnostics.

### Options

**Configure** on the integration sets:

- **Update interval** (default 60 minutes). Each poll first asks MyDramaList when your lists last changed and only downloads them when they did.
- **Lists on the episode calendar** (default Watching and Plan to Watch).

## Entities

| Entity | State | Attributes |
|--------|-------|------------|
| `sensor.mydramalist_watching` | Titles on the list | `items`, `stats` (`episodes_seen`, `mean_score`) |
| `sensor.mydramalist_completed` | Titles on the list | Same as above |
| `sensor.mydramalist_plan_to_watch` | Titles on the list | Same as above |
| `sensor.mydramalist_on_hold` | Titles on the list | Same as above |
| `sensor.mydramalist_dropped` | Titles on the list | Same as above |
| `sensor.mydramalist_total_dramas` | Titles on all lists | `count` and `stats` per list, `username`, `display_name`, `profile_url`; your avatar as the picture |
| `sensor.mydramalist_episodes_watched` | Episodes watched (MyDramaList's own count) | |
| `sensor.mydramalist_movies_watched` | Movies watched | |
| `sensor.mydramalist_time_watched` | Time watched (shown in days) | |
| `sensor.mydramalist_mean_score` | Mean of your scores | `ratings`, `score_distribution`, `reviews`, `comments`, `friends` |
| `sensor.mydramalist_unread_notifications` | Unread notifications | `friend_requests`, `messages` |
| `sensor.mydramalist_next_episode` | When the next tracked episode airs | `title`, `title_id`, `episode`, `category`, `url`, `thumb` |
| `calendar.mydramalist_episodes` | On while a tracked episode airs | Events: "Title · Episode N" |

Each entry in `items` has `id`, `name`, `url`, `thumb`, `year`, `type`, `country`, `score`, `episode_seen`, `episode_total`, `progress` (percent), `date_start`, `date_finish` and `updated_at`.

The item lists are available to templates and dashboards but are kept out of the recorder's history, since they exceed its 16 KB attribute limit. Counts and stats are recorded and have long-term statistics.

### Episode calendar

MyDramaList publishes a rolling one-week airing schedule, starting the previous day. The calendar shows the episodes in it for titles on your chosen lists, and keeps aired episodes for two weeks. Use it with a calendar trigger to get told when an episode airs:

```yaml
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.mydramalist_episodes
actions:
  - action: notify.mobile_app_phone
    data:
      title: New episode
      message: "{{ trigger.calendar_event.summary }} is out"
```

## Actions

Every action takes an optional `config_entry_id` to pick an account when you have several. Titles can be given as an id (`18452`), a slug (`18452-goblin`) or a mydramalist.com link.

### Your lists

| Action | What it does |
|--------|--------------|
| `mydramalist.mark_episode_watched` | Adds `episodes` (default 1) to the episodes you've seen and moves the title to Watching. After the last episode it moves the title to Completed, unless `complete_when_finished: false`. A title on none of your lists is added. |
| `mydramalist.update_entry` | Sets `status` (list), `episode_seen`, `score` (0–10), `date_start`, `date_finish`, `times_rewatched` or `note`. Fields you leave out keep their values. Use it with a `status` to add a title. |
| `mydramalist.remove_entry` | Removes a title from your lists. |
| `mydramalist.refresh` | Fetches your lists and the airing schedule now. |

```yaml
action: mydramalist.mark_episode_watched
data:
  title_id: "https://mydramalist.com/18452-goblin"
```

```yaml
action: mydramalist.update_entry
data:
  title_id: 36269
  status: plan_to_watch
```

The write actions return the saved entry. MyDramaList refuses some changes, such as scoring a show that hasn't aired, and the action fails with its reason.

### Looking things up

These return data for scripts and automations (use `response_variable`):

| Action | Returns |
|--------|---------|
| `mydramalist.search` | Titles and people matching `query` |
| `mydramalist.get_drama` | A title's details, cast, and your entry for it (`my_entry`) |
| `mydramalist.get_recommendations` | Titles fans of a title recommend |
| `mydramalist.get_titles` | A feed: `trending`, `top_airing`, `upcoming`, `currently_watching` or `top_movies` |
| `mydramalist.get_airing_schedule` | This week's episodes, for your calendar lists or (`only_tracked: false`) everything |

## Dashboard cards

The integration serves three cards and loads them on every dashboard; find them under **Add card** by searching for MyDramaList. All three have a visual editor.

```yaml
type: custom:mydramalist-list-card
entity: sensor.mydramalist_watching
sort: recent          # recent, progress, score or name
layout: list          # list, or grid for posters
max_items: 10
show_watched_button: true   # a +1 episode button per title
```

```yaml
type: custom:mydramalist-upcoming-card
entity: calendar.mydramalist_episodes
max_items: 8
```

```yaml
type: custom:mydramalist-stats-card
entity: sensor.mydramalist_total_dramas
```

[examples/dashboard.yaml](examples/dashboard.yaml) is a complete dashboard with these cards, the episode calendar and statistics graphs. Paste it into a new dashboard's raw configuration editor.

If the cards don't show up after updating, reload the page with the browser cache cleared. As a fallback, add `/mydramalist_static/mydramalist-card.js` as a JavaScript module resource.

## Template examples

List your completed dramas in a markdown card:

```jinja2
{% for item in state_attr('sensor.mydramalist_completed', 'items') %}
- [{{ item.name }}]({{ item.url }}) ({{ item.score }}/10) — {{ item.episode_seen }}/{{ item.episode_total }} eps
{% endfor %}
```

Dramas you're more than halfway through:

```jinja2
{{ state_attr('sensor.mydramalist_watching', 'items')
   | selectattr('progress', 'ge', 50) | map(attribute='name') | join(', ') }}
```

## Requirements

- Home Assistant 2026.6 or later (mydramalist-client needs pydantic 2.13.4+)
- A MyDramaList account
- Internet access to reach `app-api.mydramalist.com`

## Upgrading

### From 0.2.x

- The total dramas sensor no longer repeats every list's `items`; read them from the list sensors. Its per-list `count` and `stats` are unchanged.
- `stats` on the list sensors gains `mean_score`, and items gain `url`, `thumb`, `year`, `type`, `country`, `progress`, `date_start`, `date_finish` and `updated_at`.
- `mydramalist.search` returns a `url` for each drama, and `mydramalist.get_drama` adds `url`, `thumb` and `my_entry`.
- `mydramalist.refresh` no longer takes an entity target; pass `config_entry_id` to refresh one account.

### From 0.1.x

Version 0.2.0 replaced the Kuryana scraper with the MyDramaList app API:

- Existing entries are migrated automatically. Your profile slug becomes the username, and Home Assistant asks for your password through a re-authentication notice. If your login username differs from your profile slug, remove the entry and add it again.
- The custom API URL option is gone.
- `score`, `episode_seen` and `episode_total` are now numbers, and `id` is the numeric MyDramaList title id.
- Kuryana's `stats` (Dramas, TV Shows, Episodes, Movies, Days) are replaced by `stats.episodes_seen`.
- `mydramalist.get_drama` takes `title_id` instead of `slug`, and both services return the app API's fields.

## License

MIT
