/*
 * Lovelace cards for the MyDramaList integration. Served by the integration and
 * loaded on every dashboard; no separate install needed.
 *
 *   custom:mydramalist-list-card      a list (Watching, Completed, ...) with posters
 *   custom:mydramalist-upcoming-card  upcoming episodes of the titles on your lists
 *   custom:mydramalist-stats-card     watch time, episodes, mean score and list sizes
 */

const DOMAIN = "mydramalist";
const VERSION = "0.3.0";
const CATEGORIES = ["watching", "completed", "plan_to_watch", "on_hold", "dropped"];
const CATEGORY_LABELS = {
  watching: "Watching",
  completed: "Completed",
  plan_to_watch: "Plan to Watch",
  on_hold: "On Hold",
  dropped: "Dropped",
};
const CATEGORY_ICONS = {
  watching: "mdi:play-circle-outline",
  completed: "mdi:check-circle-outline",
  plan_to_watch: "mdi:bookmark-outline",
  on_hold: "mdi:pause-circle-outline",
  dropped: "mdi:close-circle-outline",
};

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

// Only http(s) links and images from the API make it into the markup.
const safeUrl = (value) => (typeof value === "string" && /^https?:\/\//.test(value) ? value : "");

// i.mydramalist.com serves the same image as ..t.jpg (thumb) and ..m.jpg (medium).
const mediumImage = (thumb) => (thumb ? thumb.replace(/t\.jpg$/, "m.jpg") : thumb);

/** Entities of this integration, by translation key, for the device owning `anchor`. */
function integrationEntities(hass, anchor) {
  const entries = Object.values(hass.entities || {}).filter((e) => e.platform === DOMAIN);
  let deviceId = anchor ? hass.entities?.[anchor]?.device_id : undefined;
  if (!deviceId) deviceId = entries.find((e) => e.translation_key === "total")?.device_id;
  const found = {};
  for (const entry of entries) {
    if (entry.device_id === deviceId && entry.translation_key) {
      found[entry.translation_key] = entry.entity_id;
    }
  }
  return found;
}

function findEntity(hass, key, fallback) {
  return integrationEntities(hass)[key] || fallback;
}

function timeZoneOptions(hass) {
  // Follow the user's "use server time zone" profile setting.
  return hass.locale?.time_zone === "server" && hass.config?.time_zone
    ? { timeZone: hass.config.time_zone }
    : {};
}

function fireNotification(element, message) {
  element.dispatchEvent(
    new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }),
  );
}

const BASE_STYLE = `
  ha-card { overflow: hidden; }
  .header {
    display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
    padding: 16px 16px 8px; font-size: var(--ha-card-header-font-size, 1.5em);
    color: var(--ha-card-header-color, var(--primary-text-color));
  }
  .header .count { font-size: 0.6em; color: var(--secondary-text-color); }
  .empty { padding: 8px 16px 16px; color: var(--secondary-text-color); }
  a { color: inherit; text-decoration: none; }
  a:hover .name { text-decoration: underline; }
  .meta { color: var(--secondary-text-color); font-size: 0.85em; }
  img.poster {
    flex: none; width: 46px; height: 64px; object-fit: cover; border-radius: 6px;
    background: var(--secondary-background-color);
  }
  .placeholder {
    flex: none; width: 46px; height: 64px; border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    background: var(--secondary-background-color); color: var(--secondary-text-color);
  }
`;

class MyDramaListBaseCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this._config = { ...this.constructor.defaults(), ...config };
    this._lastKey = undefined;
    if (this._hass) this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _update() {
    if (!this._config || !this._hass) return;
    const key = this._renderKey();
    if (key === this._lastKey) return;
    this._lastKey = key;
    this.shadowRoot.innerHTML = this._render();
    this._bind?.();
  }

  getCardSize() {
    return 3;
  }

  static defaults() {
    return {};
  }
}

/* ------------------------------------------------------------------ list card */

class MyDramaListListCard extends MyDramaListBaseCard {
  static defaults() {
    return { max_items: 10, sort: "recent", layout: "list", show_watched_button: false };
  }

  static getStubConfig(hass) {
    return {
      entity: findEntity(hass, "watching", "sensor.mydramalist_watching"),
      show_watched_button: true,
    };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { integration: DOMAIN, domain: "sensor" } } },
        { name: "title", selector: { text: {} } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "max_items", selector: { number: { min: 1, max: 100, mode: "box" } } },
            {
              name: "sort",
              selector: {
                select: {
                  mode: "dropdown",
                  options: [
                    { value: "recent", label: "Recently updated" },
                    { value: "progress", label: "Progress" },
                    { value: "score", label: "Score" },
                    { value: "name", label: "Name" },
                  ],
                },
              },
            },
            {
              name: "layout",
              selector: {
                select: {
                  mode: "dropdown",
                  options: [
                    { value: "list", label: "List" },
                    { value: "grid", label: "Poster grid" },
                  ],
                },
              },
            },
          ],
        },
        { name: "show_watched_button", selector: { boolean: {} } },
      ],
      computeLabel: (schema) =>
        ({
          entity: "List sensor",
          title: "Title",
          max_items: "Items to show",
          sort: "Sort by",
          layout: "Layout",
          show_watched_button: "Show a +1 episode button",
        })[schema.name],
    };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Set entity to a MyDramaList list sensor");
    super.setConfig(config);
  }

  getCardSize() {
    return 1 + Math.min(this._items().length, this._config?.max_items ?? 10);
  }

  _state() {
    return this._hass.states[this._config.entity];
  }

  _items() {
    const items = [...(this._state()?.attributes.items || [])];
    const sorters = {
      recent: (a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")),
      progress: (a, b) => (b.progress ?? -1) - (a.progress ?? -1),
      score: (a, b) => (b.score || 0) - (a.score || 0),
      name: (a, b) => String(a.name || "").localeCompare(String(b.name || "")),
    };
    return items.sort(sorters[this._config.sort] || sorters.recent);
  }

  _renderKey() {
    const state = this._state();
    return [state?.last_updated, state?.state, JSON.stringify(this._config), this._pending].join("|");
  }

  _render() {
    const state = this._state();
    // "MyDramaList Watching" -> "Watching": the device name adds nothing on the card.
    const title =
      this._config.title ??
      (state?.attributes.friendly_name || "MyDramaList").replace(/^MyDramaList (?=\S)/, "");
    if (!state) {
      return `<style>${BASE_STYLE}</style><ha-card><div class="header">${esc(title)}</div>
        <div class="empty">Entity ${esc(this._config.entity)} not found.</div></ha-card>`;
    }
    const items = this._items().slice(0, this._config.max_items);
    const body = !items.length
      ? `<div class="empty">Nothing on this list.</div>`
      : this._config.layout === "grid"
        ? `<div class="grid">${items.map((i) => this._gridItem(i)).join("")}</div>`
        : `<div class="rows">${items.map((i) => this._row(i)).join("")}</div>`;
    return `<style>${BASE_STYLE}${LIST_STYLE}</style>
      <ha-card>
        <div class="header"><span>${esc(title)}</span><span class="count">${esc(state.state)}</span></div>
        ${body}
      </ha-card>`;
  }

  _poster(item) {
    const src = safeUrl(item.thumb);
    return src
      ? `<img class="poster" src="${esc(src)}" alt="" loading="lazy">`
      : `<div class="placeholder"><ha-icon icon="mdi:television-classic"></ha-icon></div>`;
  }

  _progressText(item) {
    if (item.episode_total) return `${item.episode_seen ?? 0}/${item.episode_total}`;
    return item.episode_seen ? `${item.episode_seen} seen` : "";
  }

  _row(item) {
    const meta = [item.year, item.country, item.type].filter(Boolean).map(esc).join(" · ");
    const progress = item.progress ?? (item.episode_total ? 0 : null);
    const pending = this._pending === item.id;
    const finished = item.episode_total && item.episode_seen >= item.episode_total;
    const button =
      this._config.show_watched_button && !finished
        ? `<ha-icon-button class="watched" data-id="${esc(item.id)}" label="Mark next episode watched"
             ${pending ? "disabled" : ""}><ha-icon icon="${pending ? "mdi:loading" : "mdi:plus"}"></ha-icon></ha-icon-button>`
        : "";
    return `<div class="row">
      <a href="${esc(safeUrl(item.url))}" target="_blank" rel="noreferrer">${this._poster(item)}</a>
      <div class="info">
        <a href="${esc(safeUrl(item.url))}" target="_blank" rel="noreferrer"><div class="name">${esc(item.name)}</div></a>
        <div class="meta">${meta}</div>
        ${
          progress === null
            ? ""
            : `<div class="progress"><div class="bar"><div style="width:${Math.min(100, Number(progress) || 0)}%"></div></div>
               <span class="meta">${esc(this._progressText(item))}</span></div>`
        }
      </div>
      ${item.score ? `<div class="score"><ha-icon icon="mdi:star"></ha-icon>${esc(item.score)}</div>` : ""}
      ${button}
    </div>`;
  }

  _gridItem(item) {
    const src = safeUrl(mediumImage(item.thumb));
    const progress = item.progress;
    return `<a class="tile" href="${esc(safeUrl(item.url))}" target="_blank" rel="noreferrer" title="${esc(item.name)}">
      ${src ? `<img src="${esc(src)}" alt="" loading="lazy">` : `<div class="tile-fallback">${esc(item.name)}</div>`}
      ${item.score ? `<span class="badge"><ha-icon icon="mdi:star"></ha-icon>${esc(item.score)}</span>` : ""}
      ${progress != null && progress < 100 ? `<div class="tile-bar"><div style="width:${Number(progress) || 0}%"></div></div>` : ""}
      <div class="tile-name">${esc(item.name)}</div>
    </a>`;
  }

  _bind() {
    this.shadowRoot.querySelectorAll(".watched").forEach((button) => {
      button.addEventListener("click", (ev) => this._markWatched(ev, Number(button.dataset.id)));
    });
  }

  async _markWatched(ev, titleId) {
    ev.preventDefault();
    ev.stopPropagation();
    if (this._pending) return;
    this._pending = titleId;
    this._update();
    try {
      await this._hass.callService(DOMAIN, "mark_episode_watched", { title_id: titleId });
    } catch (err) {
      fireNotification(this, err?.message || String(err));
    } finally {
      this._pending = undefined;
      this._update();
    }
  }
}

const LIST_STYLE = `
  .rows { padding: 0 8px 8px; }
  .row { display: flex; align-items: center; gap: 12px; padding: 6px 8px; border-radius: 8px; }
  .row:hover { background: var(--secondary-background-color); }
  .info { flex: 1; min-width: 0; }
  .name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .progress { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
  .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
  .bar > div { height: 100%; background: var(--primary-color); border-radius: 3px; }
  .score { display: flex; align-items: center; gap: 2px; color: var(--secondary-text-color); font-size: 0.9em; }
  .score ha-icon, .badge ha-icon { --mdc-icon-size: 16px; color: var(--warning-color, #f4b400); }
  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
    gap: 10px; padding: 0 16px 16px;
  }
  .tile { position: relative; display: block; border-radius: 8px; overflow: hidden;
    aspect-ratio: 2 / 3; background: var(--secondary-background-color); }
  .tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .tile-fallback { padding: 8px; font-size: 0.85em; }
  .tile-name {
    position: absolute; inset: auto 0 0 0; padding: 18px 6px 6px; font-size: 0.75em; color: #fff;
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.8));
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .tile-bar { position: absolute; inset: auto 0 0 0; height: 3px; background: rgba(255, 255, 255, 0.3); z-index: 1; }
  .tile-bar > div { height: 100%; background: var(--primary-color); }
  .badge {
    position: absolute; top: 4px; right: 4px; display: flex; align-items: center; gap: 2px;
    padding: 1px 6px; border-radius: 10px; font-size: 0.75em; color: #fff; background: rgba(0, 0, 0, 0.65);
  }
`;

/* -------------------------------------------------------------- upcoming card */

class MyDramaListUpcomingCard extends MyDramaListBaseCard {
  static defaults() {
    return { entity: "calendar.mydramalist_episodes", max_items: 8, show_aired: false };
  }

  static getStubConfig(hass) {
    return { entity: findEntity(hass, "episodes", "calendar.mydramalist_episodes") };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { integration: DOMAIN, domain: "calendar" } } },
        { name: "title", selector: { text: {} } },
        { name: "max_items", selector: { number: { min: 1, max: 50, mode: "box" } } },
        { name: "show_aired", selector: { boolean: {} } },
      ],
      computeLabel: (schema) =>
        ({
          entity: "Episode calendar",
          title: "Title",
          max_items: "Episodes to show",
          show_aired: "Include episodes that already aired",
        })[schema.name],
    };
  }

  connectedCallback() {
    // Re-fetch periodically so "aired" episodes drop off without a state change.
    this._timer = setInterval(() => this._fetch(true), 15 * 60 * 1000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  set hass(hass) {
    this._hass = hass;
    this._fetch();
    this._update();
  }

  setConfig(config) {
    super.setConfig(config);
    this._fetchedFor = undefined;
    this._airings = undefined;
    this._fetch();
  }

  _entryId() {
    // The calendar's device belongs to exactly one MyDramaList config entry.
    const deviceId = this._hass.entities?.[this._config?.entity]?.device_id;
    return this._hass.devices?.[deviceId]?.config_entries?.[0];
  }

  async _fetch(force = false) {
    if (!this._hass || !this._config) return;
    const stamp = this._hass.states[this._config.entity]?.last_updated;
    if (!force && (this._fetching || stamp === this._fetchedFor)) return;
    this._fetching = true;
    this._fetchedFor = stamp;
    try {
      const data = { only_tracked: true };
      const entryId = this._entryId();
      if (entryId) data.config_entry_id = entryId;
      const result = await this._hass.callWS({
        type: "call_service",
        domain: DOMAIN,
        service: "get_airing_schedule",
        service_data: data,
        return_response: true,
      });
      this._airings = result.response.airings;
      this._error = undefined;
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._fetching = false;
      this._lastKey = undefined;
      this._update();
    }
  }

  _renderKey() {
    return [JSON.stringify(this._config), this._airings?.length, this._fetchedFor, this._error, Math.floor(Date.now() / 60000)].join("|");
  }

  _render() {
    const title = this._config.title ?? "Upcoming episodes";
    let body;
    if (this._error) body = `<div class="empty">${esc(this._error)}</div>`;
    else if (!this._airings) body = `<div class="empty">Loading…</div>`;
    else {
      const now = Date.now();
      const airings = this._airings
        .filter((a) => this._config.show_aired || new Date(a.end).getTime() > now)
        .slice(0, this._config.max_items);
      body = airings.length
        ? this._grouped(airings)
        : `<div class="empty">No upcoming episodes of the titles on your lists this week.</div>`;
    }
    return `<style>${BASE_STYLE}${UPCOMING_STYLE}</style>
      <ha-card><div class="header"><span>${esc(title)}</span></div>${body}</ha-card>`;
  }

  _dayLabel(date) {
    const lang = this._hass.locale?.language || navigator.language;
    const tz = timeZoneOptions(this._hass);
    const key = (d) => d.toLocaleDateString("en-CA", tz);
    const today = new Date();
    const tomorrow = new Date(today.getTime() + 86400000);
    if (key(date) === key(today)) return "Today";
    if (key(date) === key(tomorrow)) return "Tomorrow";
    return date.toLocaleDateString(lang, { weekday: "long", month: "short", day: "numeric", ...tz });
  }

  _grouped(airings) {
    const lang = this._hass.locale?.language || navigator.language;
    const tz = timeZoneOptions(this._hass);
    const groups = [];
    for (const airing of airings) {
      const start = new Date(airing.start);
      const label = this._dayLabel(start);
      if (groups.at(-1)?.label !== label) groups.push({ label, airings: [] });
      groups.at(-1).airings.push({ airing, start });
    }
    const now = Date.now();
    return groups
      .map(
        (group) => `<div class="day">${esc(group.label)}</div>
        ${group.airings
          .map(({ airing, start }) => {
            const live = start.getTime() <= now && new Date(airing.end).getTime() > now;
            const time = start.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit", ...tz });
            const meta = [airing.episode ? `Episode ${airing.episode}` : airing.type, airing.country]
              .filter(Boolean)
              .map(esc)
              .join(" · ");
            const src = safeUrl(airing.thumb);
            return `<a class="airing" href="${esc(safeUrl(airing.url))}" target="_blank" rel="noreferrer">
              ${src ? `<img class="poster" src="${esc(src)}" alt="" loading="lazy">` : `<div class="placeholder"><ha-icon icon="mdi:calendar-star"></ha-icon></div>`}
              <div class="info"><div class="name">${esc(airing.title)}</div><div class="meta">${meta}</div></div>
              <div class="time ${live ? "live" : ""}">${live ? "Airing" : esc(time)}</div>
            </a>`;
          })
          .join("")}`,
      )
      .join("");
  }
}

const UPCOMING_STYLE = `
  .day { padding: 8px 16px 4px; font-size: 0.8em; font-weight: 500; text-transform: uppercase;
    letter-spacing: 0.05em; color: var(--secondary-text-color); }
  .airing { display: flex; align-items: center; gap: 12px; padding: 6px 16px; }
  .airing:hover { background: var(--secondary-background-color); }
  .airing:last-child { padding-bottom: 12px; }
  .info { flex: 1; min-width: 0; }
  .name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .time { font-variant-numeric: tabular-nums; color: var(--secondary-text-color); }
  .time.live { color: var(--primary-color); font-weight: 500; }
`;

/* ----------------------------------------------------------------- stats card */

class MyDramaListStatsCard extends MyDramaListBaseCard {
  static getStubConfig(hass) {
    return { entity: findEntity(hass, "total", "sensor.mydramalist_total_dramas") };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { integration: DOMAIN, domain: "sensor" } } },
        { name: "title", selector: { text: {} } },
      ],
      computeLabel: (schema) => ({ entity: "Total dramas sensor", title: "Title" })[schema.name],
    };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Set entity to the MyDramaList total dramas sensor");
    super.setConfig(config);
  }

  _entities() {
    return integrationEntities(this._hass, this._config.entity);
  }

  _renderKey() {
    const ids = Object.values(this._entities());
    return [JSON.stringify(this._config), ...ids.map((id) => this._hass.states[id]?.last_updated)].join("|");
  }

  _value(key) {
    const id = this._entities()[key];
    const state = id && this._hass.states[id];
    if (!state || ["unknown", "unavailable"].includes(state.state)) return undefined;
    return state;
  }

  _format(state, digits = 0) {
    const number = Number(state.state);
    if (Number.isNaN(number)) return state.state;
    const lang = this._hass.locale?.language || navigator.language;
    return number.toLocaleString(lang, { maximumFractionDigits: digits });
  }

  _render() {
    const total = this._hass.states[this._config.entity];
    if (!total) {
      return `<style>${BASE_STYLE}</style><ha-card><div class="empty">Entity ${esc(this._config.entity)} not found.</div></ha-card>`;
    }
    const attrs = total.attributes;
    const name = this._config.title ?? attrs.display_name ?? attrs.username ?? "MyDramaList";
    const avatar = safeUrl(attrs.entity_picture);
    const tiles = [
      ["time_watched", "mdi:timer-sand", "Time watched", 1],
      ["episodes_watched", "mdi:filmstrip", "Episodes", 0],
      ["movies_watched", "mdi:movie-open-outline", "Movies", 0],
      ["mean_score", "mdi:star-outline", "Mean score", 2],
    ]
      .map(([key, icon, label, digits]) => {
        const state = this._value(key);
        if (!state) return "";
        const unit = state.attributes.unit_of_measurement;
        const suffix =
          key === "time_watched" && unit ? `<span class="unit">${esc(unit === "d" ? "days" : unit)}</span>` : "";
        return `<div class="tile"><ha-icon icon="${icon}"></ha-icon>
          <div class="value">${esc(this._format(state, digits))}${suffix}</div><div class="label">${label}</div></div>`;
      })
      .join("");
    const lists = CATEGORIES.map((category) => {
      const count = attrs[category]?.count;
      if (count == null) return "";
      return `<div class="list"><ha-icon icon="${CATEGORY_ICONS[category]}"></ha-icon>
        <span class="label">${CATEGORY_LABELS[category]}</span><span class="count">${esc(count)}</span></div>`;
    }).join("");
    const profile = safeUrl(attrs.profile_url);
    return `<style>${BASE_STYLE}${STATS_STYLE}</style>
      <ha-card>
        <a class="profile" ${profile ? `href="${esc(profile)}" target="_blank" rel="noreferrer"` : ""}>
          ${avatar ? `<img class="avatar" src="${esc(avatar)}" alt="">` : `<ha-icon class="avatar" icon="mdi:account-circle"></ha-icon>`}
          <div><div class="name">${esc(name)}</div><div class="meta">${esc(total.state)} titles on MyDramaList</div></div>
        </a>
        ${tiles ? `<div class="tiles">${tiles}</div>` : ""}
        <div class="lists">${lists}</div>
      </ha-card>`;
  }
}

const STATS_STYLE = `
  .profile { display: flex; align-items: center; gap: 12px; padding: 16px; }
  .avatar { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; --mdc-icon-size: 48px; color: var(--secondary-text-color); }
  .name { font-size: 1.2em; font-weight: 500; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; padding: 0 16px 12px; }
  .unit { font-size: 0.6em; font-weight: 400; margin-left: 4px; color: var(--secondary-text-color); }
  .tile { padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color); }
  .tile ha-icon { --mdc-icon-size: 20px; color: var(--primary-color); }
  .value { font-size: 1.4em; font-weight: 500; margin-top: 4px; font-variant-numeric: tabular-nums; }
  .label { color: var(--secondary-text-color); font-size: 0.85em; }
  .lists { padding: 0 8px 12px; }
  .list { display: flex; align-items: center; gap: 12px; padding: 6px 8px; }
  .list ha-icon { color: var(--secondary-text-color); }
  .list .label { flex: 1; color: var(--primary-text-color); font-size: 1em; }
  .list .count { font-variant-numeric: tabular-nums; color: var(--secondary-text-color); }
`;

/* --------------------------------------------------------------- registration */

const CARDS = [
  ["mydramalist-list-card", MyDramaListListCard, "MyDramaList list", "A MyDramaList list with posters, progress and scores."],
  ["mydramalist-upcoming-card", MyDramaListUpcomingCard, "MyDramaList upcoming episodes", "Episodes airing soon for the titles on your lists."],
  ["mydramalist-stats-card", MyDramaListStatsCard, "MyDramaList stats", "Watch time, episodes, mean score and list sizes."],
];

window.customCards = window.customCards || [];
for (const [type, cls, name, description] of CARDS) {
  if (!customElements.get(type)) customElements.define(type, cls);
  if (!window.customCards.some((card) => card.type === type)) {
    window.customCards.push({ type, name, description, preview: true, documentationURL: "https://github.com/danieyal/ha-mydramalist#dashboard-cards" });
  }
}

console.info(`%c MYDRAMALIST-CARDS %c ${VERSION} `, "color:#fff;background:#00b4d8;font-weight:700", "color:#00b4d8");
