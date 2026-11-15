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

/** How often screen 5's counts are refreshed, in ms. */
const COUNTS_EVERY_MS = 4000;
/** How long to wait before trying again after the internet dropped, in ms. */
const RETRY_OFFLINE_MS = 45000;
/** The Rust side's answer when the library's lock is held elsewhere. */
const ALREADY_RUNNING = "An update of this library is already running.";
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
    $("pause").textContent = progress.running ? "Pause" : "Resume";
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

let retryTimer = null;

/** Start (or resume) the download; true when this window now runs it. */
async function startUpdate() {
  clearTimeout(retryTimer);
  try {
    await invoke("start_update");
    updateRunning = true;
    $("pause").textContent = "Pause";
    showProgress("Starting…");
    return true;
  } catch (error) {
    if (String(error) === ALREADY_RUNNING) {
      showProgress("Downloading in the background…");
    } else {
      toast(String(error));
    }
    return false;
  }
}

/** Bytes in a gigabyte, for screen 2. */
const GB = 1024 * 1024 * 1024;

async function showFolder() {
  show("folder");
  try {
    const folder = await invoke("library_folder");
    $("folder-path").textContent = folder.path;
    const free = folder.free_bytes === null ? "unknown" : `${(folder.free_bytes / GB).toFixed(0)} GB free`;
    $("folder-space").textContent = `${free}. A topic library needs about ${(folder.estimate_bytes / GB).toFixed(0)} GB.`;
  } catch (error) {
    toast(String(error), "bad");
  }
}

/** One status line per setup step, updated in place. */
function setStep(line) {
  let item = document.querySelector(`#step-list li[data-step="${line.step}"]`);
  if (!item) {
    item = document.createElement("li");
    item.dataset.step = line.step;
    const state = document.createElement("span");
    state.className = "state";
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = line.label;
    const text = document.createElement("span");
    text.className = "text";
    item.append(state, label, text);
    $("step-list").append(item);
  }
  item.className = line.state;
  item.querySelector(".text").textContent = line.text;
  if (line.state === "warning") toast(`${line.label}: ${line.text}`);
}

async function startSetup() {
  show("installing");
  $("installing-continue").disabled = true;
  $("installing-retry").hidden = true;
  try {
    await invoke("start_setup");
  } catch (error) {
    toast(String(error), "bad");
  }
}

async function showTopics() {
  show("topic");
  const list = $("topic-list");
  list.replaceChildren();
  const topics = await invoke("topic_counts");
  topics.forEach((topic, index) => {
    const label = document.createElement("label");
    label.className = "topic";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "topic";
    radio.value = topic.id;
    radio.checked = index === 0;
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = topic.name;
    const count = document.createElement("span");
    count.className = "count";
    count.textContent = `${topic.count.toLocaleString()} papers${topic.live ? "" : " (as last counted)"}`;
    label.append(radio, name, count);
    list.append(label);
  });
}

async function chooseTopic() {
  const id = document.querySelector('input[name="topic"]:checked')?.value;
  const when = document.querySelector('input[name="schedule"]:checked').value;
  const schedule = when === "every" ? { every: { days: Number($("schedule-days").value) } } : when;
  $("topic-start").disabled = true;
  try {
    await invoke("choose_topic", { id });
    show("building");
    await startUpdate();
    // Only now: the scheduler starts an update at once, which must find this
    // window's update holding the library's lock.
    const note = await invoke("set_schedule", { schedule });
    if (note) toast(note);
    refreshCounts();
  } catch (error) {
    toast(String(error), "bad");
  } finally {
    $("topic-start").disabled = false;
  }
}

function wire() {
  $("welcome-start").addEventListener("click", showFolder);
  $("folder-continue").addEventListener("click", startSetup);
  $("installing-retry").addEventListener("click", startSetup);
  $("installing-continue").addEventListener("click", showTopics);
  $("topic-start").addEventListener("click", chooseTopic);
  tauri.event.listen("setup-step", (event) => setStep(event.payload));
  tauri.event.listen("setup-done", (event) => {
    if (event.payload) {
      $("installing-continue").disabled = false;
    } else {
      $("installing-retry").hidden = false;
      toast("A step did not finish; see its line, then try again.", "bad");
    }
  });
  $("search-form").addEventListener("submit", runSearch);
  $("back").addEventListener("click", () => show("search"));
  $("go-search").addEventListener("click", () => show("search"));
  $("show-building").addEventListener("click", () => { show("building"); refreshCounts(); });
  $("pause").addEventListener("click", async () => {
    if (updateRunning) {
      await invoke("pause_update");
      showProgress("Pausing after the paper in flight…");
    } else {
      await startUpdate();
    }
  });
  tauri.event.listen("library-progress", (event) => showProgress(event.payload));
  tauri.event.listen("library-done", (event) => {
    updateRunning = false;
    $("pause").textContent = "Resume";
    showProgress(event.payload.message);
    $("search-progress").hidden = event.payload.complete;
    if (event.payload.waiting) {
      // Try again by itself once the internet may be back.
      retryTimer = setTimeout(startUpdate, RETRY_OFFLINE_MS);
    }
    refreshCounts();
  });
  // Screen 5's counts move whoever runs the update (this window, or a
  // scheduled one in the background).
  setInterval(() => {
    if (updateRunning || !$("screen-building").hidden) refreshCounts();
  }, COUNTS_EVERY_MS);
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
