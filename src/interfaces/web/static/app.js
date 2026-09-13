"use strict";

// Consume the Phase 19 API contract as-is (docs/architecture/domain-model-and-api.md).

async function api(spec, options = {}) {
  const [method, path] = spec.split(" ");
  const response = await fetch(path, { method, ...options });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const reason =
      (body && (body.reason || body.message || body.detail)) ||
      `request failed (${response.status})`;
    const error = new Error(reason);
    error.status = response.status;
    throw error;
  }
  return body;
}

function showError(element, error) {
  element.textContent = `Error ${error.status || ""}: ${error.message}`.trim();
  element.hidden = false;
}

async function createGame(form, button, errorEl) {
  errorEl.hidden = true;
  errorEl.textContent = "";
  button.disabled = true;
  try {
    const payload = { campaign_name: form.elements.campaign_name.value };
    const seedRaw = form.elements.seed.value.trim();
    if (seedRaw !== "") {
      payload.seed = Number.parseInt(seedRaw, 10);
    }
    const created = await api("POST /api/v1/games", {
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(payload),
    });
    sessionStorage.setItem("game_id", created.game_id);
    if (created.opening && created.opening.narration) {
      sessionStorage.setItem("opening_narration", created.opening.narration);
    }
    if (created.opening && created.opening.npc_reply) {
      sessionStorage.setItem("opening_npc_reply", created.opening.npc_reply);
    }
    window.location.href = "/games/" + encodeURIComponent(created.game_id);
  } catch (error) {
    showError(errorEl, error);
    button.disabled = false;
  }
}

function bootLobby() {
  const form = document.getElementById("new-game-form");
  if (!form) return;
  const button = document.getElementById("create-game");
  const errorEl = document.getElementById("lobby-error");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    createGame(form, button, errorEl);
  });
}

const POLL_INTERVAL_MS = 2500;

// Event-feed formatter table. Keys are wire event_type values (snake_case,
// derived from the domain event class names in src/domain/events/events.py);
// lines use payload fields only, verified against that file's dataclass
// fields (BaseEvent.to_payload serializes fields verbatim).
const EVENT_FORMATTERS = {
  game_created: (p) => `Campaign created (seed ${p.seed ?? "-"})`,
  game_started: () => "The game begins.",
  initiative_rolled: (p, n) => `${n(p.character_id)} rolls initiative: ${p.total ?? "-"}`,
  combat_started: (p) =>
    `Combat begins — round ${p.round_number ?? "-"} (${(p.participant_ids || []).length} participants)`,
  turn_started: (p, n) => `Round ${p.round_number ?? "-"}: ${n(p.actor_id)}'s turn`,
  turn_ended: (p, n) => `Round ${p.round_number ?? "-"}: ${n(p.actor_id)} ends their turn`,
  attack_requested: (p, n) => `${n(p.attacker_id)} attacks ${n(p.target_id)} with ${p.weapon_id ?? "-"}`,
  attack_resolved: (p, n) => {
    const outcome = p.critical ? "CRITICAL HIT" : p.hit ? "hit" : "miss";
    return (
      `${n(p.attacker_id)} attacks ${n(p.target_id)}: d20 ${p.roll ?? "-"} +` +
      ` ${p.attack_bonus ?? "-"} = ${p.total ?? "-"} vs AC ${p.target_ac ?? "-"}` +
      ` — ${outcome}`
    );
  },
  damage_applied: (p, n) =>
    `${n(p.character_id)} takes ${p.amount ?? "-"} damage (${p.hp_before ?? "-"} → ${p.hp_after ?? "-"})`,
  character_defeated: (p, n) => `${n(p.character_id)} is defeated!`,
  action_rejected: (p) => `Action rejected (${p.action_type ?? "-"}): ${p.reason ?? "-"}`,
  combat_ended: (p) => `Combat ends — ${p.winner_side ?? "-"} wins in round ${p.round_number ?? "-"}`,
};

function formatEvent(envelope, nameById = {}) {
  const payload = envelope.payload || {};
  const resolve = (id) => (nameById && nameById[id]) || String(id ?? "-");
  const formatter = EVENT_FORMATTERS[envelope.event_type];
  if (!formatter) {
    // Unknown type: show it verbatim plus the raw payload (never lie by omission).
    return `— ${envelope.event_type}\n${JSON.stringify(payload)}`;
  }
  return formatter(payload, resolve);
}

let lastSeq = 0; // highest event sequence already rendered (client-side filtering)
let pollTimer = null;
let pollInFlight = false;

function parseGameId() {
  const marker = "/games/";
  const index = window.location.pathname.indexOf(marker);
  if (index === -1) return null;
  const raw = window.location.pathname.slice(index + marker.length);
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function loadLastSeq(gameId) {
  const stored = sessionStorage.getItem(`last_seq:${gameId}`);
  if (stored === null) return 0;
  const value = Number.parseInt(stored, 10);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function persistLastSeq(gameId) {
  sessionStorage.setItem(`last_seq:${gameId}`, String(lastSeq));
}

function formatEvent(envelope) {
  // Generic Task-3 line; Task 5 replaces this with a per-type formatter table.
  return `${envelope.event_type} ${JSON.stringify(envelope.payload)}`;
}

function appendEvent(envelope, nameById) {
  const feed = document.getElementById("event-feed");
  if (!feed) return;
  const item = document.createElement("li");
  // textContent only — model data is never assigned to markup.
  item.textContent = `[${envelope.sequence}] ${formatEvent(envelope, nameById)}`;
  feed.prepend(item); // newest on top
}

function ingestEvents(gameId, envelopes, nameById) {
  const fresh = envelopes.filter((env) => env.sequence > lastSeq);
  for (const env of fresh) appendEvent(env, nameById);
  if (fresh.length > 0) {
    lastSeq = Math.max(lastSeq, ...fresh.map((env) => env.sequence));
    persistLastSeq(gameId);
  }
}

// Task 4: panels render from server fields ONLY (GameView contract), never
// from derived rules math. The only "condition" computed client-side is the
// is_defeated styling sent by the API.

function buildElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function hpBarPercent(hpCurrent, hpMax) {
  // Presentation only: width of the bar visual, clamped 0..100.
  if (!hpMax || hpMax <= 0) return 0;
  const percent = (hpCurrent / hpMax) * 100;
  if (!Number.isFinite(percent)) return 0;
  return Math.min(100, Math.max(0, percent));
}

function appendConditionTags(row, member) {
  const tags = buildElement("span", "condition-tags");
  for (const condition of member.conditions || []) {
    tags.appendChild(buildElement("span", "condition-tag", condition ?? "-"));
  }
  if (member.is_defeated) {
    tags.appendChild(buildElement("span", "condition-tag condition-defeated", "defeated"));
  }
  row.appendChild(tags);
}

function appendHpBar(row, member) {
  const hpMax = member.hp_max ?? 0;
  const hpCurrent = member.hp_current ?? 0;
  const bar = buildElement("span", "hp-bar");
  const fill = buildElement("span", "hp-fill");
  fill.style.width = `${hpBarPercent(hpCurrent, hpMax)}%`;
  bar.appendChild(fill);
  row.appendChild(bar);
  row.appendChild(buildElement("span", "hp-text", `${hpCurrent} / ${hpMax}`));
}

function rosterRow(member, isParty) {
  const row = buildElement("li", isParty ? "roster-row party" : "roster-row enemy");
  if (member.is_defeated) row.classList.add("defeated");
  row.appendChild(buildElement("span", "member-name", member.name ?? "-"));
  row.appendChild(
    buildElement(
      "span",
      "member-class",
      `${member.character_class ?? "-"} · level ${member.level ?? "-"}`,
    ),
  );
  appendHpBar(row, member);
  row.appendChild(buildElement("span", "member-ac", `AC ${member.armor_class ?? "-"}`));
  appendConditionTags(row, member);
  return row;
}

// Shared roster builder: party roster (emphasis) and enemies (no emphasis).
function renderParty(container, members, { isParty = true } = {}) {
  if (!container) return;
  const list = members || [];
  if (list.length === 0) {
    container.hidden = true;
    return;
  }
  container.hidden = false;
  container.replaceChildren(); // idempotent re-render each poll
  container.appendChild(buildElement("h2", null, isParty ? "Party" : "Enemies"));
  const rows = buildElement("ul", "roster");
  for (const member of list) rows.appendChild(rosterRow(member, isParty));
  container.appendChild(rows);
}

// Combat tracker: hidden entirely when combat is null (status line stays).
function renderCombatTracker(view) {
  const tracker = document.getElementById("combat-tracker");
  if (!tracker) return;
  const combat = (view && view.combat) || null;
  if (!combat) {
    tracker.hidden = true;
    tracker.replaceChildren();
    return;
  }
  tracker.hidden = false;
  tracker.replaceChildren(); // idempotent re-render each poll
  tracker.appendChild(
    buildElement("h2", null, `Combat — round ${combat.round_number ?? "-"} (${combat.status ?? "-"})`),
  );
  const order = buildElement("ul", "initiative-order");
  for (const entry of combat.initiative_order || []) {
    const item = buildElement("li", "initiative-entry");
    if (combat.active_actor_id && entry.character_id === combat.active_actor_id) {
      item.classList.add("active-actor");
    }
    item.appendChild(buildElement("span", "initiative-name", entry.name ?? "-"));
    item.appendChild(buildElement("span", "initiative-total", `${entry.total ?? "-"}`));
    order.appendChild(item);
  }
  tracker.appendChild(order);
}

function render(status, view) {
  const statusLine = document.getElementById("status-line");
  if (!statusLine) return;
  const combat = (view && view.combat) || null;
  let text = `Game status: ${(status && status.status) ?? "-"}`;
  if (combat) {
    text += ` — combat round ${combat.round_number} (${combat.status})`;
  }
  if (status.game_over) {
    text += " — game over";
  }
  statusLine.textContent = text;
  renderParty(document.getElementById("party-panel"), view && view.party, { isParty: true });
  renderParty(document.getElementById("enemies-panel"), view && view.enemies, { isParty: false });
  renderCombatTracker(view);
}

function nameMapFromView(view) {
  // Presentation-only id→name lookup for event feed lines; unknown ids fall
  // back to the raw id inside formatEvent.
  const map = {};
  const members = (view && view.party) || [];
  const enemies = (view && view.enemies) || [];
  for (const member of [...members, ...enemies]) {
    if (member && member.id) map[member.id] = member.name ?? member.id;
  }
  return map;
}

async function pollOnce(gameId, errorEl) {
  const [status, view] = await Promise.all([
    api(`GET /api/v1/games/${gameId}/status`),
    api(`GET /api/v1/games/${gameId}`),
  ]);
  if (status.game_over) {
    stopPolling();
  }
  render(status, view);
  const feed = await api(`GET /api/v1/games/${gameId}/events`);
  ingestEvents(gameId, feed.events || [], nameMapFromView(view));
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPolling(gameId, errorEl) {
  if (pollTimer !== null) return;
  const tick = async () => {
    if (pollInFlight) return; // guard against overlapping in-flight requests
    pollInFlight = true;
    try {
      await pollOnce(gameId, errorEl);
      errorEl.hidden = true;
      errorEl.textContent = "";
    } catch (error) {
      // Polling errors never kill the timer; only game_over stops the loop.
      showError(errorEl, error);
    } finally {
      pollInFlight = false;
    }
  };
  tick();
  pollTimer = setInterval(tick, POLL_INTERVAL_MS);
}

function bootGame() {
  const leadIn = document.getElementById("lead-in");
  if (!leadIn) return;
  const narration = sessionStorage.getItem("opening_narration");
  if (narration) {
    leadIn.textContent = narration;
    leadIn.hidden = false;
  }
  const gameId = parseGameId();
  if (!gameId) return;
  lastSeq = loadLastSeq(gameId);
  const errorEl = document.getElementById("game-error");
  startPolling(gameId, errorEl);
}

function boot() {
  const page = document.body.dataset.page;
  if (page === "lobby") bootLobby();
  if (page === "game") bootGame();
}

boot();
