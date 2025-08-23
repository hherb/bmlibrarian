"""
BMLibrarian Configuration GUI Application

Provides a tabbed interface for configuring BMLibrarian agents and settings.
"""

import flet as ft
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

from ..config import get_config, DEFAULT_CONFIG
from .tabs import GeneralSettingsTab, AgentConfigTab


class BMLibrarianConfigApp:
    """Main configuration application using Flet."""
    
    def __init__(self):
        self.config = get_config()
        self.page: Optional[ft.Page] = None
        self.tabs: Dict[str, Any] = {}
        self.tab_objects: Dict[str, Any] = {}  # Store actual tab objects for updates
        
    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        page.title = "BMLibrarian Configuration"
        page.window.width = 1000
        page.window.height = 750
        page.window.min_width = 800
        page.window.min_height = 650
        page.window.resizable = True
        page.theme_mode = ft.ThemeMode.LIGHT
        
        # Create tabs
        self._create_tabs()
        
        # Create main layout
        main_tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=list(self.tabs.values()),
            expand=True
        )
        
        # Create action buttons with more prominent styling
        action_buttons = ft.Column([
            # First row - main actions
            ft.Row([
                ft.ElevatedButton(
                    "Save to ~/.bmlibrarian",
                    icon=ft.Icons.SAVE,
                    on_click=self._save_to_default,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.GREEN_600,
                        color=ft.Colors.WHITE
                    ),
                    height=40,
                    width=200,
                    tooltip="Save to default config location"
                ),
                ft.ElevatedButton(
                    "Save As...",
                    icon=ft.Icons.SAVE_AS,
                    on_click=self._save_config,
                    height=40,
                    width=140
                ),
                ft.ElevatedButton(
                    "Load Configuration",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=self._load_config,
                    height=40,
                    width=180
                ),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            # Second row - utility actions  
            ft.Row([
                ft.ElevatedButton(
                    "Reset to Defaults",
                    icon=ft.Icons.REFRESH,
                    on_click=self._reset_defaults,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.ORANGE_600,
                        color=ft.Colors.WHITE
                    ),
                    height=35,
                    width=160
                ),
                ft.ElevatedButton(
                    "Test Connection",
                    icon=ft.Icons.WIFI,
                    on_click=self._test_connection,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLUE_600,
                        color=ft.Colors.WHITE
                    ),
                    height=35,
                    width=160
                )
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
        ], spacing=5)
        
        # Create main layout - simple structure without expand conflicts
        page.add(
            ft.Column([
                # Header
                ft.Container(
                    ft.Text(
                        "BMLibrarian Configuration",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_700
                    ),
                    margin=ft.margin.only(bottom=20)
                ),
                # Main tabs with fixed height
                ft.Container(
                    main_tabs,
                    height=450,  # Fixed height to prevent infinite expansion
                    width=None   # Let width be automatic
                ),
                # Action buttons - make them clearly visible
                ft.Container(
                    action_buttons,
                    margin=ft.margin.only(top=20),
                    padding=ft.padding.all(15),
                    bgcolor=ft.Colors.GREY_100,  # Light background to make buttons stand out
                    border_radius=10,
                    width=None,  # Full width
                    height=120  # Accommodate two rows of buttons
                )
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO  # Allow page scrolling if needed
            )
        )
        
    def _create_tabs(self):
        """Create all configuration tabs."""
        # General Settings Tab
        general_tab = GeneralSettingsTab(self)
        self.tab_objects['general'] = general_tab  # Store reference
        self.tabs['general'] = ft.Tab(
            text="General Settings",
            icon=ft.Icons.SETTINGS,
            content=general_tab.build()
        )
        
        # Agent Configuration Tabs
        agent_types = {
            'query_agent': ('Query Agent', ft.Icons.SEARCH),
            'scoring_agent': ('Scoring Agent', ft.Icons.SCORE),
            'citation_agent': ('Citation Agent', ft.Icons.FORMAT_QUOTE),
            'reporting_agent': ('Reporting Agent', ft.Icons.DESCRIPTION),
            'counterfactual_agent': ('Counterfactual Agent', ft.Icons.PSYCHOLOGY),
            'editor_agent': ('Editor Agent', ft.Icons.EDIT)
        }
        
        for agent_key, (display_name, icon) in agent_types.items():
            agent_tab = AgentConfigTab(self, agent_key, display_name)
            self.tab_objects[agent_key] = agent_tab  # Store reference
            self.tabs[agent_key] = ft.Tab(
                text=display_name,
                icon=icon,
                content=agent_tab.build()
            )
    
    def _load_config(self, e):
        """Load configuration from file."""
        def file_picker_result(result: ft.FilePickerResultEvent):
            if result.files:
                try:
                    file_path = result.files[0].path
                    with open(file_path, 'r') as f:
                        config_data = json.load(f)
                    
                    # Update configuration
                    self.config._merge_config(config_data)
                    
                    # Refresh all tabs
                    self._refresh_all_tabs()
                    
                    self._show_success_dialog("Configuration loaded successfully!")
                    
                except Exception as ex:
                    self._show_error_dialog(f"Failed to load configuration: {str(ex)}")
        
        file_picker = ft.FilePicker(on_result=file_picker_result)
        self.page.overlay.append(file_picker)
        self.page.update()
        
        file_picker.pick_files(
            dialog_title="Load Configuration File",
            allowed_extensions=["json"],
            file_type=ft.FilePickerFileType.CUSTOM
        )
    
    def _save_config(self, e):
        """Save current configuration to file."""
        def file_picker_result(result: ft.FilePickerResultEvent):
            if result.path:
                try:
                    print(f"💾 Starting save process to: {result.path}")  # Debug
                    
                    # Show current config state before update
                    print(f"📊 Config before update: {len(str(self.config._config))} chars")
                    
                    # Update config from UI before saving
                    self._update_config_from_ui()
                    
                    # Show config state after update
                    print(f"📊 Config after update: {len(str(self.config._config))} chars")
                    
                    # Save configuration
                    file_path = result.path
                    if not file_path.endswith('.json'):
                        file_path += '.json'
                    
                    print(f"💾 Saving config to: {file_path}")  # Debug
                    print(f"💾 Config content preview: {str(self.config._config)[:200]}...")  # Debug
                    self.config.save_config(file_path)
                    
                    # Verify the file was created
                    import os
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        print(f"✅ File saved successfully: {file_size} bytes")  # Debug
                        self._show_success_dialog(f"✅ Configuration saved to {file_path}\nFile size: {file_size} bytes")
                    else:
                        print("❌ File was not created")  # Debug
                        self._show_error_dialog("❌ Configuration file was not created")
                    
                except Exception as ex:
                    print(f"❌ Save error: {ex}")  # Debug
                    self._show_error_dialog(f"Failed to save configuration: {str(ex)}")
        
        file_picker = ft.FilePicker(on_result=file_picker_result)
        self.page.overlay.append(file_picker)
        self.page.update()
        
        file_picker.save_file(
            dialog_title="Save Configuration File",
            file_name="config.json",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"]
        )
    
    def _save_to_default(self, e):
        """Save configuration to default location ~/.bmlibrarian/config.json"""
        try:
            import os
            
            print("💾 Saving to default location...")  # Debug
            
            # Update config from UI before saving
            self._update_config_from_ui()
            
            # Save to default location (None means use default)
            self.config.save_config(None)
            
            # Get the actual path that was used
            default_path = os.path.expanduser("~/.bmlibrarian/config.json")
            
            # Verify the file was created
            if os.path.exists(default_path):
                file_size = os.path.getsize(default_path)
                print(f"✅ File saved successfully: {file_size} bytes")  # Debug
                self._show_success_dialog(f"✅ Configuration saved to default location!\n\n{default_path}\nFile size: {file_size} bytes")
            else:
                print("❌ File was not created at default location")  # Debug
                self._show_error_dialog("❌ Configuration file was not created at default location")
                
        except Exception as ex:
            print(f"❌ Save to default error: {ex}")  # Debug
            self._show_error_dialog(f"Failed to save configuration to default location: {str(ex)}")
    
    def _reset_defaults(self, e):
        """Reset configuration to defaults."""
        def confirm_reset(result):
            if result:
                # Reset to defaults
                self.config._config = DEFAULT_CONFIG.copy()
                self._refresh_all_tabs()
                self._show_success_dialog("Configuration reset to defaults!")
        
        self._show_confirm_dialog(
            "Reset to Defaults",
            "Are you sure you want to reset all settings to defaults? This will overwrite current settings.",
            confirm_reset
        )
    
    def _test_connection(self, e):
        """Test connection to Ollama server."""
        try:
            import ollama
            
            # Create client to test connection
            host = self.config.get_ollama_config()['host']
            client = ollama.Client(host=host)
            
            # Get available models
            models_response = client.list()
            models = [model.model for model in models_response.models]
            
            if models:
                model_list = '\n'.join(models[:10])  # Show first 10 models
                if len(models) > 10:
                    model_list += f"\n... and {len(models) - 10} more models"
                
                self._show_success_dialog(f"✅ Connection successful to {host}\n\nFound {len(models)} models:\n{model_list}")
            else:
                self._show_success_dialog(f"✅ Connected to {host}\nBut no models are installed.")
                
        except Exception as ex:
            self._show_error_dialog(f"❌ Connection test failed: {str(ex)}\n\nPlease check:\n• Ollama server is running\n• Host URL is correct\n• Network connectivity")
    
    def _update_config_from_ui(self):
        """Update configuration from all UI components."""
        try:
            # Update general settings
            general_tab = self.tab_objects.get('general')
            if general_tab and hasattr(general_tab, 'update_config'):
                general_tab.update_config()
            
            # Update agent tabs
            agent_types = ['query_agent', 'scoring_agent', 'citation_agent', 'reporting_agent', 'counterfactual_agent', 'editor_agent']
            for agent_key in agent_types:
                agent_tab = self.tab_objects.get(agent_key)
                if agent_tab and hasattr(agent_tab, 'update_config'):
                    agent_tab.update_config()
                    
            print("✅ Configuration updated from UI")  # Debug output
                    
        except Exception as ex:
            print(f"❌ Error updating config from UI: {ex}")  # Debug output
            self._show_error_dialog(f"Failed to update configuration from UI: {str(ex)}")
    
    def _refresh_all_tabs(self):
        """Refresh all tabs with current configuration."""
        # This will be implemented by individual tabs
        if self.page:
            self.page.update()
    
    def _show_success_dialog(self, message: str):
        """Show success dialog."""
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Success", color=ft.Colors.GREEN_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda _: self._close_dialog())
            ]
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _show_error_dialog(self, message: str):
        """Show error dialog."""
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Error", color=ft.Colors.RED_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda _: self._close_dialog())
            ]
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _show_confirm_dialog(self, title: str, message: str, callback):
        """Show confirmation dialog."""
        def handle_result(result):
            self._close_dialog()
            callback(result)
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title, color=ft.Colors.ORANGE_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: handle_result(False)),
                ft.TextButton("Confirm", on_click=lambda _: handle_result(True))
            ]
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _close_dialog(self):
        """Close the current dialog."""
        if self.page.overlay:
            self.page.overlay.clear()
            self.page.update()


def run_config_app():
    """Run the configuration application as desktop app."""
    app = BMLibrarianConfigApp()
    ft.app(target=app.main, view=ft.FLET_APP)