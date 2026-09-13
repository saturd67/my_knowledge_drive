import flet as ft

from view.theme import Space, palette
from view.widgets.containers.icon_badge import IconBadge


class EmptyState(ft.Container):
    """Centred placeholder for a list or panel with nothing in it."""

    def __init__(self, icon, heading, message, action=None, height=260):
        super().__init__()
        self.icon = icon
        self.heading = heading
        self.message = message
        self.action = action
        self.height = height

    def build(self):
        p = palette()
        children = [
            IconBadge(self.icon, "neutral", size=56, icon_size=26),
            ft.Container(height=Space.LG),
            ft.Text(self.heading, size=15, weight=ft.FontWeight.W_700, color=p.text),
            ft.Text(self.message, size=13, color=p.text_muted, text_align=ft.TextAlign.CENTER),
        ]
        if self.action is not None:
            children += [ft.Container(height=Space.LG), self.action]

        self.content = ft.Column(
            children,
            spacing=2,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        self.alignment = ft.Alignment.CENTER
