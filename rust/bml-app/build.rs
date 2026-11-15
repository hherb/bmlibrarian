//! Tauri's build step: embeds `tauri.conf.json`, the capabilities and `ui/`.

fn main() {
    tauri_build::build();
}
