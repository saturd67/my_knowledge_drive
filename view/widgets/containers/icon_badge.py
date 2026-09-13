import flet as ft

from view.theme import Radius, tone


class IconBadge(ft.Container):
    """Square tinted tile holding one icon."""

    def __init__(self, icon, tone_name="primary", size=42, icon_size=20):
        super().__init__()
        self.icon = icon
        self.tone_name = tone_name
        self.size = size
        self.icon_size = icon_size

    def build(self):
        fg, bg = tone(self.tone_name)
        self.content = ft.Icon(self.icon, size=self.icon_size, color=fg)
        self.width = self.size
        self.height = self.size
        self.bgcolor = bg
        self.border_radius = Radius.MD
        self.alignment = ft.Alignment.CENTER
