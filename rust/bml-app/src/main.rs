//! BMLibrarian's app window (Tauri): a thin front end over `bml-setup`,
//! `bml-library` and `bml-search`. Developer notes: `doc/developers/bml_app.md`.

// No console window behind the app on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod state;

use std::path::PathBuf;

use state::StartScreen;

/// What every command shares: the configuration folder of this run.
struct App {
    config_dir: PathBuf,
}

/// The screen to open on (`welcome` or `search`).
#[tauri::command]
fn start_screen(app: tauri::State<'_, App>) -> StartScreen {
    state::start_screen(&app.config_dir)
}

fn main() {
    let config_dir = match state::config_dir() {
        Ok(dir) => dir,
        Err(e) => {
            eprintln!("BMLibrarian cannot find its settings folder: {e}");
            std::process::exit(1);
        }
    };
    if let Err(e) = tauri::Builder::default()
        .manage(App { config_dir })
        .invoke_handler(tauri::generate_handler![start_screen])
        .run(tauri::generate_context!())
    {
        eprintln!("BMLibrarian's window could not open: {e}");
        std::process::exit(1);
    }
}
