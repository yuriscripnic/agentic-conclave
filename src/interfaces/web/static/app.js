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

function bootGame() {
  const leadIn = document.getElementById("lead-in");
  if (!leadIn) return;
  const narration = sessionStorage.getItem("opening_narration");
  if (narration) {
    leadIn.textContent = narration;
    leadIn.hidden = false;
  }
}

function boot() {
  const page = document.body.dataset.page;
  if (page === "lobby") bootLobby();
  if (page === "game") bootGame();
}

boot();
