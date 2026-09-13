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

function appendEvent(envelope) {
  const feed = document.getElementById("event-feed");
  if (!feed) return;
  const item = document.createElement("li");
  item.textContent = `[${envelope.sequence}] ${formatEvent(envelope)}`;
  feed.prepend(item); // newest on top
}

function ingestEvents(gameId, envelopes) {
  const fresh = envelopes.filter((env) => env.sequence > lastSeq);
  for (const env of fresh) appendEvent(env);
  if (fresh.length > 0) {
    lastSeq = Math.max(lastSeq, ...fresh.map((env) => env.sequence));
    persistLastSeq(gameId);
  }
}

function render(status) {
  // Owner of the party/enemies/combat containers. Task 4 fills in the
  // per-panel rendering; for now the panels stay hidden and status text only.
  const statusLine = document.getElementById("status-line");
  if (!statusLine) return;
  let text = `Game status: ${status.status}`;
  if (status.combat) {
    text += ` — combat round ${status.combat.round_number} (${status.combat.status})`;
  }
  if (status.game_over) {
    text += " — game over";
  }
  statusLine.textContent = text;
}

async function pollOnce(gameId, errorEl) {
  const status = await api(`GET /api/v1/games/${gameId}/status`);
  if (status.game_over) {
    stopPolling();
  }
  render(status);
  const feed = await api(`GET /api/v1/games/${gameId}/events`);
  ingestEvents(gameId, feed.events || []);
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
