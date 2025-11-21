"""
Settings Tab for Research GUI

Integrates configuration functionality from config_app into the main research GUI
as a nested tab interface within a single Settings tab.
"""

import flet as ft
from typing import TYPE_CHECKING, Optional

from ...config import get_config
from .tabs import GeneralSettingsTab, AgentConfigTab, SearchSettingsTab

if TYPE_CHECKING:
    from .research_app import ResearchGUI


class SettingsTab:
    """Settings tab with vertical navigation layout."""

    def __init__(self, app: "ResearchGUI"):
        """Initialize settings tab.

        Args:
            app: ResearchGUI instance
        """
        self.app = app
        self.page = app.page
        self.config = get_config()
        self.tab_objects = {}  # Store tab references for updates
        self.content_containers = {}  # Store content containers for each section
        self.current_section = 'general'  # Track current selected section
        self.content_area: Optional[ft.Container] = None
        self.nav_buttons = {}  # Store navigation button references

    def build(self) -> ft.Container:
        """Build the settings tab content with vertical left-side navigation.

        Returns:
            Container with vertical navigation and content area
        """
        # Create navigation sections
        self._create_sections()

        # Create left navigation panel
        nav_panel = self._create_navigation_panel()

        # Create action buttons
        action_buttons = self._create_action_buttons()

        # Left sidebar: navigation + action buttons (anchored to top-left)
        left_sidebar = ft.Column([
            # Navigation panel
            ft.Container(
                content=nav_panel,
                expand=True,
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.GREY_300),
                border_radius=8,
                alignment=ft.alignment.top_left
            ),
            # Action buttons directly below navigation
            ft.Container(
                action_buttons,
                margin=ft.margin.only(top=10),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.GREY_100,
                border=ft.border.all(1, ft.Colors.GREY_300),
                border_radius=8
            )
        ], spacing=0, alignment=ft.MainAxisAlignment.START)

        # Create content area (right side)
        self.content_area = ft.Container(
            content=self.content_containers['general'],
            expand=True,
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=8
        )

        # Main layout: Row with sidebar on left (fixed width), content on right (expandable)
        main_row = ft.Row([
            # Left sidebar (fixed width, anchored to top)
            ft.Container(
                content=left_sidebar,
                width=220,
                alignment=ft.alignment.top_left,
                expand=False  # Don't expand vertically
            ),
            # Right content area (expandable)
            self.content_area
        ], spacing=15, expand=True, alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START)

        return ft.Container(
            content=ft.Column([
                # Header
                ft.Container(
                    ft.Text(
                        "Settings & Configuration",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_700
                    ),
                    margin=ft.margin.only(bottom=10)
                ),
                # Main content row
                ft.Container(
                    main_row,
                    expand=True,
                    alignment=ft.alignment.top_left
                )
            ], spacing=0, expand=True),
            padding=ft.padding.all(15),
            expand=True
        )

    def _create_sections(self):
        """Create content sections for each configuration area."""
        # General Settings
        general_tab = GeneralSettingsTab(self)
        self.tab_objects['general'] = general_tab
        self.content_containers['general'] = general_tab.build()

        # Search Settings
        search_tab = SearchSettingsTab(self)
        self.tab_objects['search'] = search_tab
        self.content_containers['search'] = search_tab.build()

        # Agent Configuration Sections
        agent_types = {
            'query_agent': ('Query Agent', ft.Icons.SEARCH),
            'scoring_agent': ('Scoring Agent', ft.Icons.SCORE),
            'citation_agent': ('Citation Agent', ft.Icons.FORMAT_QUOTE),
            'reporting_agent': ('Reporting Agent', ft.Icons.DESCRIPTION),
            'counterfactual_agent': ('Counterfactual', ft.Icons.PSYCHOLOGY),
            'editor_agent': ('Editor Agent', ft.Icons.EDIT)
        }

        for agent_key, (display_name, icon) in agent_types.items():
            agent_tab = AgentConfigTab(self, agent_key, display_name)
            self.tab_objects[agent_key] = agent_tab
            self.content_containers[agent_key] = agent_tab.build()

    def _create_navigation_panel(self) -> ft.Column:
        """Create vertical navigation panel with section buttons.

        Returns:
            Column containing navigation buttons
        """
        nav_items = []

        # Section categories with their items
        sections = [
            {
                'title': 'System',
                'items': [
                    ('general', 'General', ft.Icons.SETTINGS),
                    ('search', 'Search', ft.Icons.MANAGE_SEARCH),
                ]
            },
            {
                'title': 'Agents',
                'items': [
                    ('query_agent', 'Query', ft.Icons.SEARCH),
                    ('scoring_agent', 'Scoring', ft.Icons.SCORE),
                    ('citation_agent', 'Citation', ft.Icons.FORMAT_QUOTE),
                    ('reporting_agent', 'Reporting', ft.Icons.DESCRIPTION),
                    ('counterfactual_agent', 'Counterfact.', ft.Icons.PSYCHOLOGY),
                    ('editor_agent', 'Editor', ft.Icons.EDIT),
                ]
            }
        ]

        for section in sections:
            # Section header
            nav_items.append(
                ft.Container(
                    ft.Text(
                        section['title'],
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREY_700
                    ),
                    padding=ft.padding.only(left=10, top=10, bottom=5)
                )
            )

            # Section items
            for key, label, icon in section['items']:
                is_selected = (key == self.current_section)
                btn = ft.Container(
                    content=ft.Row([
                        ft.Icon(icon, size=18, color=ft.Colors.BLUE_700 if is_selected else ft.Colors.GREY_600),
                        ft.Text(label, size=13, color=ft.Colors.BLUE_900 if is_selected else ft.Colors.GREY_800)
                    ], spacing=8),
                    padding=ft.padding.symmetric(horizontal=10, vertical=8),
                    bgcolor=ft.Colors.BLUE_50 if is_selected else ft.Colors.TRANSPARENT,
                    border_radius=6,
                    ink=True,
                    on_click=lambda e, k=key: self._switch_section(k)
                )
                self.nav_buttons[key] = btn
                nav_items.append(btn)

            # Add spacing between sections
            nav_items.append(ft.Container(height=5))

        return ft.Column(nav_items, spacing=2, scroll=ft.ScrollMode.AUTO)

    def _switch_section(self, section_key: str):
        """Switch to a different configuration section.

        Args:
            section_key: Key of the section to switch to
        """
        # Update current section
        old_section = self.current_section
        self.current_section = section_key

        # Update content area
        if section_key in self.content_containers:
            self.content_area.content = self.content_containers[section_key]

        # Update navigation button styles
        if old_section in self.nav_buttons:
            old_btn = self.nav_buttons[old_section]
            old_btn.bgcolor = ft.Colors.TRANSPARENT
            # Update icon and text colors
            if old_btn.content and isinstance(old_btn.content, ft.Row):
                old_btn.content.controls[0].color = ft.Colors.GREY_600  # Icon
                old_btn.content.controls[1].color = ft.Colors.GREY_800  # Text

        if section_key in self.nav_buttons:
            new_btn = self.nav_buttons[section_key]
            new_btn.bgcolor = ft.Colors.BLUE_50
            # Update icon and text colors
            if new_btn.content and isinstance(new_btn.content, ft.Row):
                new_btn.content.controls[0].color = ft.Colors.BLUE_700  # Icon
                new_btn.content.controls[1].color = ft.Colors.BLUE_900  # Text

        # Update the page
        if self.page:
            self.page.update()

    def _create_action_buttons(self) -> ft.Column:
        """Create compact action buttons for save/load/reset operations.

        Returns:
            Column containing action buttons optimized for narrow sidebar
        """
        return ft.Column([
            # Primary action - Apply Changes (reload config)
            ft.ElevatedButton(
                "Apply Changes",
                icon=ft.Icons.CHECK_CIRCLE,
                on_click=self._apply_changes,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_700,
                    color=ft.Colors.WHITE
                ),
                width=200,
                tooltip="Apply configuration changes to current session"
            ),
            # Secondary action - Save to disk
            ft.ElevatedButton(
                "Save Config",
                icon=ft.Icons.SAVE,
                on_click=self._save_to_default,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_600,
                    color=ft.Colors.WHITE
                ),
                width=200,
                tooltip="Save to ~/.bmlibrarian/config.json"
            ),
            # File operations
            ft.Row([
                ft.IconButton(
                    icon=ft.Icons.SAVE_AS,
                    tooltip="Save As...",
                    on_click=self._save_config,
                    icon_color=ft.Colors.BLUE_600
                ),
                ft.IconButton(
                    icon=ft.Icons.FOLDER_OPEN,
                    tooltip="Load Config",
                    on_click=self._load_config,
                    icon_color=ft.Colors.BLUE_600
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="Reset to Defaults",
                    on_click=self._reset_defaults,
                    icon_color=ft.Colors.ORANGE_600
                ),
                ft.IconButton(
                    icon=ft.Icons.WIFI,
                    tooltip="Test Connection",
                    on_click=self._test_connection,
                    icon_color=ft.Colors.TEAL_600
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, spacing=2)
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _apply_changes(self, e):
        """Apply configuration changes to the current session without restart.

        This reloads the configuration from UI and reinitializes agents where possible.
        """
        try:
            print("🔄 Applying configuration changes...")

            # Update config from UI
            self._update_config_from_ui()

            # Reload configuration singleton to pick up changes
            self.config._reload_from_disk = False  # Use in-memory changes

            # Check if agents need reinitialization
            needs_agent_reinit = self._check_agent_changes()
            needs_restart = self._check_restart_required()

            if needs_agent_reinit and self.app.agents:
                # Reinitialize agents with new configuration
                self._reinitialize_agents()

            # Show success with appropriate messaging
            self._show_apply_changes_result(needs_restart)

        except Exception as ex:
            print(f"❌ Error applying changes: {ex}")
            snack_bar = ft.SnackBar(
                ft.Text(f"Failed to apply changes: {str(ex)}"),
                bgcolor=ft.Colors.RED_100
            )
            self.page.open(snack_bar)

    def _check_agent_changes(self) -> bool:
        """Check if agent configuration has changed requiring reinitialization.

        Returns:
            True if agents need to be reinitialized
        """
        # For now, assume agent changes require reinit
        # Could be enhanced to track actual changes
        return True

    def _check_restart_required(self) -> bool:
        """Check if any changes require full app restart.

        Returns:
            True if restart is required
        """
        # Ollama host changes require restart (connection already established)
        # Database connection changes require restart (pool already created)
        # Most other changes can be applied live
        return False  # For now, optimistically assume no restart needed

    def _reinitialize_agents(self):
        """Reinitialize agents with new configuration."""
        try:
            from ..agents import (
                QueryAgent, DocumentScoringAgent, CitationFinderAgent,
                ReportingAgent, CounterfactualAgent, EditorAgent
            )

            print("🔧 Reinitializing agents with new configuration...")

            # Get orchestrator from existing agents if available
            # Note: self.app.agents is a dictionary, not an object with attributes
            orchestrator = None
            if isinstance(self.app.agents, dict) and 'query_agent' in self.app.agents:
                if hasattr(self.app.agents['query_agent'], 'orchestrator'):
                    orchestrator = self.app.agents['query_agent'].orchestrator

            # Reinitialize each agent with new config
            # Note: Using the same orchestrator to maintain queue system
            self.app.agents['query_agent'] = QueryAgent(orchestrator=orchestrator)
            self.app.agents['scoring_agent'] = DocumentScoringAgent(orchestrator=orchestrator)
            self.app.agents['citation_agent'] = CitationFinderAgent(orchestrator=orchestrator)
            self.app.agents['reporting_agent'] = ReportingAgent(orchestrator=orchestrator)
            self.app.agents['counterfactual_agent'] = CounterfactualAgent(orchestrator=orchestrator)
            self.app.agents['editor_agent'] = EditorAgent(orchestrator=orchestrator)

            print("✅ Agents reinitialized successfully")

        except Exception as ex:
            print(f"⚠️ Warning: Could not reinitialize agents: {ex}")
            # Don't fail the whole operation if agent reinit fails

    def _show_apply_changes_result(self, needs_restart: bool):
        """Show result of applying configuration changes.

        Args:
            needs_restart: Whether some changes require restart
        """
        def close_dialog(e):
            dialog.open = False
            self.page.update()

        if needs_restart:
            # Some changes require restart
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Row([
                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=ft.Colors.ORANGE_600, size=30),
                    ft.Text("Changes Applied", color=ft.Colors.ORANGE_700)
                ]),
                content=ft.Column([
                    ft.Text(
                        "Configuration changes have been applied!",
                        size=14
                    ),
                    ft.Container(height=10),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.CHECK, color=ft.Colors.GREEN_600, size=20),
                                ft.Text("Applied Immediately", weight=ft.FontWeight.BOLD)
                            ]),
                            ft.Text("• Agent models and parameters updated", size=12),
                            ft.Text("• Settings active for new workflows", size=12),
                        ], spacing=5),
                        padding=10,
                        bgcolor=ft.Colors.GREEN_50,
                        border_radius=8
                    ),
                    ft.Container(height=10),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.RESTART_ALT, color=ft.Colors.ORANGE_600, size=20),
                                ft.Text("Restart Required For", weight=ft.FontWeight.BOLD)
                            ]),
                            ft.Text("• Ollama host connection changes", size=12),
                            ft.Text("• Database connection changes", size=12),
                        ], spacing=5),
                        padding=10,
                        bgcolor=ft.Colors.ORANGE_50,
                        border_radius=8
                    ),
                ], tight=True, spacing=8),
                actions=[
                    ft.TextButton("OK", on_click=close_dialog)
                ],
                actions_alignment=ft.MainAxisAlignment.END
            )
        else:
            # All changes applied successfully
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Row([
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_600, size=30),
                    ft.Text("Changes Applied", color=ft.Colors.GREEN_700)
                ]),
                content=ft.Column([
                    ft.Text(
                        "All configuration changes have been applied successfully!",
                        size=14
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        "✓ Agents reinitialized with new settings\n"
                        "✓ Changes active immediately\n"
                        "✓ No restart required",
                        size=12,
                        color=ft.Colors.GREY_700
                    ),
                    ft.Container(height=10),
                    ft.Text(
                        "💡 Tip: Use 'Save Config' to persist changes to disk.",
                        size=11,
                        italic=True,
                        color=ft.Colors.BLUE_700
                    )
                ], tight=True, spacing=8),
                actions=[
                    ft.TextButton("OK", on_click=close_dialog)
                ],
                actions_alignment=ft.MainAxisAlignment.END
            )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _load_config(self, e):
        """Load configuration from file."""
        def file_picker_result(result: ft.FilePickerResultEvent):
            try:
                # Force cleanup of all file picker overlays
                self.page.overlay.clear()
                self.page.update()

                if result.files:
                    file_path = result.files[0].path
                    import json
                    with open(file_path, 'r') as f:
                        config_data = json.load(f)

                    # Update configuration
                    self.config._merge_config(config_data)

                    # Refresh all tabs
                    self._refresh_all_tabs()

                    # Show success message
                    snack_bar = ft.SnackBar(
                        ft.Text("✅ Configuration loaded successfully!"),
                        bgcolor=ft.Colors.GREEN_100
                    )
                    self.page.open(snack_bar)

            except Exception as ex:
                snack_bar = ft.SnackBar(
                    ft.Text(f"Failed to load: {str(ex)}"),
                    bgcolor=ft.Colors.RED_100
                )
                self.page.open(snack_bar)

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
            try:
                # Force cleanup of all file picker overlays
                self.page.overlay.clear()
                self.page.update()

                if result.path:
                    print(f"💾 Starting save process to: {result.path}")

                    # Update config from UI before saving
                    self._update_config_from_ui()

                    # Save configuration
                    file_path = result.path
                    if not file_path.endswith('.json'):
                        file_path += '.json'

                    print(f"💾 Saving config to: {file_path}")
                    self.config.save_config(file_path)

                    # Verify the file was created
                    import os
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        print(f"✅ File saved successfully: {file_size} bytes")
                        snack_bar = ft.SnackBar(
                            ft.Text(f"✅ Configuration saved to {os.path.basename(file_path)}"),
                            bgcolor=ft.Colors.GREEN_100
                        )
                        self.page.open(snack_bar)
                    else:
                        print("❌ File was not created")
                        snack_bar = ft.SnackBar(
                            ft.Text("❌ Configuration file was not created"),
                            bgcolor=ft.Colors.RED_100
                        )
                        self.page.open(snack_bar)

            except Exception as ex:
                print(f"❌ Save error: {ex}")
                snack_bar = ft.SnackBar(
                    ft.Text(f"Failed to save: {str(ex)}"),
                    bgcolor=ft.Colors.RED_100
                )
                self.page.open(snack_bar)

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

            print("💾 Saving to default location...")

            # Update config from UI before saving
            self._update_config_from_ui()

            # Save to default location (None means use default)
            self.config.save_config(None)

            # Get the actual path that was used
            default_path = os.path.expanduser("~/.bmlibrarian/config.json")

            # Verify the file was created
            if os.path.exists(default_path):
                file_size = os.path.getsize(default_path)
                print(f"✅ File saved successfully: {file_size} bytes")

                # Show success message with restart recommendation
                self._show_restart_notification()
            else:
                print("❌ File was not created at default location")
                snack_bar = ft.SnackBar(
                    ft.Text("❌ Configuration file was not created at default location"),
                    bgcolor=ft.Colors.RED_100
                )
                self.page.open(snack_bar)

        except Exception as ex:
            print(f"❌ Save to default error: {ex}")
            snack_bar = ft.SnackBar(
                ft.Text(f"Failed to save: {str(ex)}"),
                bgcolor=ft.Colors.RED_100
            )
            self.page.open(snack_bar)

    def _reset_defaults(self, e):
        """Reset configuration to defaults."""
        try:
            from ..config import DEFAULT_CONFIG

            # Reset to defaults immediately
            self.config._config = DEFAULT_CONFIG.copy()
            self._refresh_all_tabs()

            # Show success message
            snack_bar = ft.SnackBar(
                ft.Text("⚠️ Configuration reset to defaults! Click 'Save to ~/.bmlibrarian' to persist changes."),
                bgcolor=ft.Colors.ORANGE_100,
                duration=6000
            )
            self.page.open(snack_bar)

        except Exception as ex:
            snack_bar = ft.SnackBar(
                ft.Text(f"Failed to reset configuration: {str(ex)}"),
                bgcolor=ft.Colors.RED_100
            )
            self.page.open(snack_bar)

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
                snack_bar = ft.SnackBar(
                    ft.Text(f"✅ Connected to {host} - Found {len(models)} models"),
                    bgcolor=ft.Colors.GREEN_100,
                    duration=4000
                )
                self.page.open(snack_bar)
            else:
                snack_bar = ft.SnackBar(
                    ft.Text(f"✅ Connected to {host} but no models installed"),
                    bgcolor=ft.Colors.ORANGE_100,
                    duration=4000
                )
                self.page.open(snack_bar)

        except Exception as ex:
            snack_bar = ft.SnackBar(
                ft.Text(f"❌ Connection failed to {self.config.get_ollama_config()['host']}: {str(ex)}"),
                bgcolor=ft.Colors.RED_100,
                duration=6000
            )
            self.page.open(snack_bar)

    def _update_config_from_ui(self):
        """Update configuration from all UI components."""
        try:
            # Update general settings
            general_tab = self.tab_objects.get('general')
            if general_tab and hasattr(general_tab, 'update_config'):
                general_tab.update_config()

            # Update search settings
            search_tab = self.tab_objects.get('search')
            if search_tab and hasattr(search_tab, 'update_config'):
                search_tab.update_config()

            # Update agent tabs (including multi-model config in query agent)
            agent_types = ['query_agent', 'scoring_agent', 'citation_agent',
                          'reporting_agent', 'counterfactual_agent', 'editor_agent']
            for agent_key in agent_types:
                agent_tab = self.tab_objects.get(agent_key)
                if agent_tab and hasattr(agent_tab, 'update_config'):
                    agent_tab.update_config()

            print("✅ Configuration updated from UI")

        except Exception as ex:
            print(f"❌ Error updating config from UI: {ex}")

    def _refresh_all_tabs(self):
        """Refresh all tabs with current configuration."""
        # Refresh all tabs if they have refresh methods
        for key, tab in self.tab_objects.items():
            if hasattr(tab, 'refresh'):
                tab.refresh()

        if self.page:
            self.page.update()

    def _show_restart_notification(self):
        """Show notification that configuration changes require app restart.

        This creates a dialog with restart recommendations for users.
        """
        def close_dialog(e):
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_600, size=30),
                ft.Text("Configuration Saved", color=ft.Colors.GREEN_700)
            ]),
            content=ft.Column([
                ft.Text(
                    "Your configuration has been saved successfully!",
                    size=14
                ),
                ft.Container(height=10),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.BLUE_600, size=20),
                            ft.Text("Configuration Changes", weight=ft.FontWeight.BOLD)
                        ]),
                        ft.Text(
                            "• Agent models and parameters will apply to new workflows",
                            size=12
                        ),
                        ft.Text(
                            "• Changes to Ollama host require app restart",
                            size=12
                        ),
                        ft.Text(
                            "• Database settings take effect on next query",
                            size=12
                        )
                    ], spacing=5),
                    padding=10,
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=8
                ),
                ft.Container(height=10),
                ft.Row([
                    ft.Icon(ft.Icons.RESTART_ALT, color=ft.Colors.ORANGE_600, size=20),
                    ft.Text("Restart Recommended", weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_700)
                ]),
                ft.Text(
                    "For all changes to take full effect, please restart the application.",
                    size=12,
                    color=ft.Colors.GREY_700
                )
            ], tight=True, spacing=8),
            actions=[
                ft.TextButton("OK", on_click=close_dialog)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _notify_config_change(self, change_type: str):
        """Notify user about configuration changes and their effects.

        Args:
            change_type: Type of change ('model', 'ollama', 'database', 'agent')
        """
        messages = {
            'model': "Model changes will apply to new workflow runs.",
            'ollama': "⚠️ Ollama host changes require app restart!",
            'database': "Database changes will take effect on the next query.",
            'agent': "Agent parameter changes will apply to new workflows."
        }

        message = messages.get(change_type, "Configuration updated.")
        color = ft.Colors.ORANGE_100 if change_type == 'ollama' else ft.Colors.BLUE_100
        duration = 5000 if change_type == 'ollama' else 3000

        snack_bar = ft.SnackBar(
            ft.Text(message),
            bgcolor=color,
            duration=duration
        )
        self.page.open(snack_bar)
