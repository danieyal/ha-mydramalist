# ha-mydramalist

Home Assistant custom integration for [MyDramaList](https://mydramalist.com) powered by [mydramalist-client](https://pypi.org/project/mydramalist-client/) ([pymdl](https://github.com/danieyal/pymdl)), an unofficial client for the MyDramaList app API.

Tracks your drama watching progress — watching, completed, plan-to-watch, on-hold, dropped — as sensors in Home Assistant. Also provides services to search for dramas and fetch detailed info.

## Features

- **Dramalist tracking** — sensors for each list category (Completed, Plan to Watch, On Hold, Dropped, Watching) with counts and full item details as attributes
- **Account sign-in** — reads your lists straight from the MyDramaList app API, with re-authentication when your password changes
- **Services** — `mydramalist.search` to find dramas, `mydramalist.get_drama` for detailed info, `mydramalist.refresh` to force-poll
- **Diagnostics** — built-in HA diagnostics support for troubleshooting
- **Config flow** — set up entirely through the UI, no YAML needed

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
4. Click Submit

The app API only serves the signed-in user's lists, so the integration tracks the account you sign in with. Your password is stored in the Home Assistant config entry and is redacted from diagnostics.

After setup, you'll see a **MyDramaList** device with sensors:

| Sensor | State | Attributes |
|--------|-------|------------|
| `sensor.mydramalist_completed` | Count of completed dramas | `items` (name, id, score, episode_seen, episode_total) and `stats` (episodes_seen) |
| `sensor.mydramalist_plan_to_watch` | Count of plan-to-watch | Same as above |
| `sensor.mydramalist_on_hold` | Count of on-hold | Same as above |
| `sensor.mydramalist_dropped` | Count of dropped | Same as above |
| `sensor.mydramalist_watching` | Count of currently watching | Same as above |
| `sensor.mydramalist_total_dramas` | Total dramas across all lists | All categories with items and stats |

## Services

### `mydramalist.refresh`

Force an immediate refresh of dramalist data.

### `mydramalist.search`

Search MyDramaList for dramas or people.

```yaml
service: mydramalist.search
data:
  query: "goblin"
```

Returns matching dramas and people.

### `mydramalist.get_drama`

Get detailed info for a specific drama by its MyDramaList title id, or a slug that starts with it (the part of the URL after `mydramalist.com/`).

```yaml
service: mydramalist.get_drama
data:
  title_id: "18452-goblin"
```

Returns title, rating, synopsis, cast, episodes, genres, tags, and more.

## Template examples

List your completed dramas in a markdown card:

```jinja2
{% for item in state_attr('sensor.mydramalist_completed', 'items') %}
- {{ item.name }} ({{ item.score }}/10) — {{ item.episode_seen }}/{{ item.episode_total }} eps
{% endfor %}
```

Get the number of completed episodes:

```jinja2
{{ state_attr('sensor.mydramalist_total_dramas', 'completed').stats.episodes_seen }} episodes
```

## Requirements

- Home Assistant 2026.6 or later (mydramalist-client needs pydantic 2.13.4+)
- A MyDramaList account
- Internet access to reach `app-api.mydramalist.com`

## Upgrading from 0.1.x

Version 0.2.0 replaces the Kuryana scraper with the MyDramaList app API:

- Existing entries are migrated automatically. Your profile slug becomes the username, and Home Assistant asks for your password through a re-authentication notice. If your login username differs from your profile slug, remove the entry and add it again.
- The custom API URL option is gone.
- `score`, `episode_seen` and `episode_total` are now numbers, and `id` is the numeric MyDramaList title id.
- Kuryana's `stats` (Dramas, TV Shows, Episodes, Movies, Days) are replaced by `stats.episodes_seen`.
- `mydramalist.get_drama` takes `title_id` instead of `slug`, and both services return the app API's fields.

## License

MIT
