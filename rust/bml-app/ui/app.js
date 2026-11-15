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

async function start() {
  try {
    show(await invoke("start_screen"));
  } catch (error) {
    show("welcome");
    toast(String(error), "bad");
  }
}

start();
