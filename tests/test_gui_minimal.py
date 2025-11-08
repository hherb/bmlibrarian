#!/usr/bin/env python3
"""Minimal test for GUI components."""

import flet as ft

def main(page: ft.Page):
    page.title = "Test GUI"
    page.window.width = 800
    page.window.height = 600
    
    # Test ExpansionTile
    try:
        tile = ft.ExpansionTile(
            title=ft.Text("Test Step"),
            subtitle=ft.Text("Test description"),
            controls=[
                ft.Container(
                    content=ft.Text("Test content"),
                    padding=ft.padding.all(10)
                )
            ]
        )
        
        page.add(
            ft.Column([
                ft.Text("GUI Test Success!", size=24),
                tile
            ])
        )
        
    except Exception as e:
        page.add(ft.Text(f"Error: {e}", color=ft.Colors.RED))

if __name__ == '__main__':
    ft.app(target=main)