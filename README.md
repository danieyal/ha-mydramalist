# ha-mydramalist

Home Assistant custom integration for [MyDramaList](https://mydramalist.com) powered by the [Kuryana](https://github.com/tbdsux/kuryana) scraper API.

Tracks your drama watching progress — completed, plan-to-watch, on-hold, dropped — as sensors in Home Assistant. Also provides services to search for dramas and fetch detailed info.

## Features

- **Dramalist tracking** — sensors for each list category (Completed, Plan to Watch, On Hold, Dropped, Watching) with counts and full item details as attributes
- **Configurable API endpoint** — use the public Kuryana API or point to your own self-hosted instance
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
3. Enter your MyDramaList user ID (the slug in your profile URL) and optionally a custom Kuryana API endpoint
4. Click Submit

After setup, you'll see a **MyDramaList** device with sensors:

| Sensor | State | Attributes |
|--------|-------|------------|
| `sensor.mydramalist_completed` | Count of completed dramas | List of dramas with name, score, progress |
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

Get detailed info for a specific drama by its slug.

```yaml
service: mydramalist.get_drama
data:
  slug: "goblin"
```

Returns title, rating, synopsis, cast, episodes, genres, and more.

## Template examples

List your completed dramas in a markdown card:

```jinja2
{% for item in state_attr('sensor.mydramalist_completed', 'items') %}
- {{ item.name }} ({{ item.score }}/10) — {{ item.episode_seen }}/{{ item.episode_total }} eps
{% endfor %}
```

Get your total days spent watching:

```jinja2
{{ state_attr('sensor.mydramalist_total_dramas', 'completed').stats.Days }} days
```

## Requirements

- Home Assistant 2023.8 or later
- Python 3.12+ (required by kuryana)
- Internet access to reach the Kuryana API

## Self-hosting Kuryana

If you prefer to run your own Kuryana instance:

```sh
git clone https://github.com/tbdsux/kuryana
cd kuryana
docker compose up -d --build
```

Then enter `http://<your-host>:<port>` as the API URL during setup.

## License

MIT
