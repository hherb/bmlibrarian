// BMLibrarian app front end: shows one screen at a time and talks to the
// Rust side through Tauri commands and events. No framework (spec D).
"use strict";

const tauri = window.__TAURI__;
const invoke = (command, args) => tauri.core.invoke(command, args);

/** How long a toast stays, in milliseconds. */
const TOAST_MS = 6000;

/** Show screen `name` (the id after `screen-`) and hide the others. */
function show(name) {
  for (const screen of document.querySelectorAll(".screen")) {
    screen.hidden = screen.id !== `screen-${name}`;
  }
}

/** A short message in the corner that goes away by itself (never a modal). */
function toast(message, kind = "warn") {
  const box = document.createElement("div");
  box.className = `toast ${kind}`;
  box.textContent = message;
  document.getElementById("toasts").append(box);
  setTimeout(() => box.remove(), TOAST_MS);
}

/** How often screen 5's counts are refreshed while an update runs, in ms. */
const COUNTS_EVERY_MS = 4000;
/** How long a passage may be on a result card, in characters. */
const PASSAGE_CHARS = 420;

const $ = (id) => document.getElementById(id);
let updateRunning = false;

/** The text of a result card, built without HTML injection. */
function resultCard(hit) {
  const card = document.createElement("div");
  card.className = "card result";
  const title = document.createElement("h3");
  title.textContent = hit.title || "(untitled)";
  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = [hit.journal, hit.year].filter(Boolean).join(" · ");
  const passage = document.createElement("p");
  passage.className = "passage";
  const text = hit.passage.replace(/\s+/g, " ").trim();
  passage.textContent = text.length > PASSAGE_CHARS ? `${text.slice(0, PASSAGE_CHARS)}…` : text;
  card.append(title, meta, passage);
  card.addEventListener("click", () => openPaper(hit.publication_id));
  return card;
}

async function runSearch(event) {
  event.preventDefault();
  const query = $("search-box").value;
  const results = $("results");
  if (!query.trim()) {
    $("search-status").textContent = "Type what you are looking for.";
    return;
  }
  $("search-status").textContent = "Searching…";
  try {
    const hits = await invoke("search", { query });
    results.replaceChildren(...hits.map(resultCard));
    $("search-status").textContent = hits.length
      ? `${hits.length} papers, best match first.`
      : "No papers match yet.";
  } catch (error) {
    $("search-status").textContent = "";
    toast(String(error), "bad");
  }
}

async function openPaper(id) {
  try {
    const paper = await invoke("open_paper", { id });
    $("paper-title").textContent = paper.title;
    $("paper-meta").textContent = paper.meta;
    $("paper-text").textContent = paper.text;
    show("paper");
    window.scrollTo(0, 0);
  } catch (error) {
    toast(String(error), "bad");
  }
}

async function refreshCounts() {
  try {
    const progress = await invoke("library_counts");
    const c = progress.counts;
    $("count-found").textContent = c.found.toLocaleString();
    $("count-fulltext").textContent = c.full_text.toLocaleString();
    $("count-searchable").textContent = c.searchable.toLocaleString();
    $("building-eta").textContent = progress.minutes_left
      ? `About ${progress.minutes_left.toLocaleString()} minutes to go for the papers found so far.`
      : "";
    updateRunning = progress.running;
    $("pause").disabled = !progress.running;
  } catch (error) {
    // The counts are a nicety; a failed refresh is retried on the next tick.
  }
}

function showProgress(line) {
  $("building-line").textContent = line;
  const searchLine = $("search-progress");
  searchLine.textContent = line;
  searchLine.hidden = false;
}

async function startUpdate() {
  try {
    await invoke("start_update");
    updateRunning = true;
    showProgress("Starting…");
  } catch (error) {
    toast(String(error));
  }
}

function wire() {
  $("search-form").addEventListener("submit", runSearch);
  $("back").addEventListener("click", () => show("search"));
  $("go-search").addEventListener("click", () => show("search"));
  $("show-building").addEventListener("click", () => { show("building"); refreshCounts(); });
  $("pause").addEventListener("click", async () => {
    await invoke("pause_update");
    showProgress("Pausing after the paper in flight…");
  });
  tauri.event.listen("library-progress", (event) => showProgress(event.payload));
  tauri.event.listen("library-done", (event) => {
    updateRunning = false;
    showProgress(event.payload.message);
    $("search-progress").hidden = event.payload.complete;
    refreshCounts();
  });
  setInterval(() => { if (updateRunning) refreshCounts(); }, COUNTS_EVERY_MS);
}

async function start() {
  wire();
  try {
    const screen = await invoke("start_screen");
    show(screen);
    if (screen === "search") refreshCounts();
  } catch (error) {
    show("welcome");
    toast(String(error), "bad");
  }
}

start();
