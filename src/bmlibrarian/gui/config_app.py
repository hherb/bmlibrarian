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
        
    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        page.title = "BMLibrarian Configuration"
        page.window.width = 1000
        page.window.height = 700
        page.window.min_width = 800
        page.window.min_height = 600
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
        
        # Create action buttons
        action_buttons = ft.Row(
            [
                ft.ElevatedButton(
                    "Load Configuration",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=self._load_config
                ),
                ft.ElevatedButton(
                    "Save Configuration",
                    icon=ft.Icons.SAVE,
                    on_click=self._save_config,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.GREEN_600,
                        color=ft.Colors.WHITE
                    )
                ),
                ft.ElevatedButton(
                    "Reset to Defaults",
                    icon=ft.Icons.REFRESH,
                    on_click=self._reset_defaults,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.ORANGE_600,
                        color=ft.Colors.WHITE
                    )
                ),
                ft.ElevatedButton(
                    "Test Connection",
                    icon=ft.Icons.WIFI,
                    on_click=self._test_connection,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLUE_600,
                        color=ft.Colors.WHITE
                    )
                )
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10
        )
        
        # Create main layout
        page.add(
            ft.Column([
                ft.Container(
                    ft.Text(
                        "BMLibrarian Configuration",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_700
                    ),
                    margin=ft.margin.only(bottom=20)
                ),
                ft.Container(main_tabs, expand=True),
                ft.Container(
                    action_buttons,
                    margin=ft.margin.only(top=20),
                    padding=ft.padding.all(10)
                )
            ])
        )
        
    def _create_tabs(self):
        """Create all configuration tabs."""
        # General Settings Tab
        general_tab = GeneralSettingsTab(self)
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
                    # Update config from UI before saving
                    self._update_config_from_ui()
                    
                    # Save configuration
                    file_path = result.path
                    if not file_path.endswith('.json'):
                        file_path += '.json'
                    
                    self.config.save_config(file_path)
                    self._show_success_dialog(f"Configuration saved to {file_path}")
                    
                except Exception as ex:
                    self._show_error_dialog(f"Failed to save configuration: {str(ex)}")
        
        file_picker = ft.FilePicker(on_result=file_picker_result)
        self.page.overlay.append(file_picker)
        self.page.update()
        
        file_picker.save_file(
            dialog_title="Save Configuration File",
            file_name="bmlibrarian_config.json",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"]
        )
    
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
            from ..agents.base import BaseAgent
            
            # Create a temporary agent to test connection
            test_agent = BaseAgent.__new__(BaseAgent)
            test_agent.model = self.config.get_model('query_agent')
            test_agent.host = self.config.get_ollama_config()['host']
            test_agent.client = __import__('ollama').Client(host=test_agent.host)
            
            if test_agent.test_connection():
                models = test_agent.get_available_models()
                self._show_success_dialog(f"Connection successful!\nAvailable models: {', '.join(models[:5])}{'...' if len(models) > 5 else ''}")
            else:
                self._show_error_dialog("Connection test failed. Please check your Ollama server.")
                
        except Exception as ex:
            self._show_error_dialog(f"Connection test failed: {str(ex)}")
    
    def _update_config_from_ui(self):
        """Update configuration from all UI components."""
        # Update general settings
        general_tab = next((tab for tab_key, tab in self.tabs.items() if tab_key == 'general'), None)
        if hasattr(general_tab, 'content') and hasattr(general_tab.content.content, 'update_config'):
            general_tab.content.content.update_config()
        
        # Update agent tabs
        agent_types = ['query_agent', 'scoring_agent', 'citation_agent', 'reporting_agent', 'counterfactual_agent', 'editor_agent']
        for agent_key in agent_types:
            agent_tab = self.tabs.get(agent_key)
            if agent_tab and hasattr(agent_tab, 'content') and hasattr(agent_tab.content.content, 'update_config'):
                agent_tab.content.content.update_config()
    
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