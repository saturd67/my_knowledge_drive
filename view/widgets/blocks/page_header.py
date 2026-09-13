import flet as ft

from view.theme import Space, palette
from view.widgets.text.subtitle import Subtitle


class PageHeader(ft.Row):
    """Screen heading, description and the screen-level actions."""

    def __init__(self, heading, description, actions=None):
        super().__init__()
        self.heading = heading
        self.description = description
        self.actions = actions

    def build(self):
        self.controls = [
            ft.Column(
                [
                    ft.Text(self.heading, size=24, weight=ft.FontWeight.W_700,
                            color=palette().text),
                    Subtitle(self.description),
                ],
                spacing=4,
                expand=True,
            ),
            ft.Row(self.actions or [], spacing=Space.SM),
        ]
        self.vertical_alignment = ft.CrossAxisAlignment.CENTER
