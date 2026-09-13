import flet as ft

from view.theme import Radius, tone


class Pill(ft.Container):
    """Rounded status tag, optionally led by an icon."""

    def __init__(self, text, tone_name="neutral", icon=None):
        super().__init__()
        self.text = text
        self.tone_name = tone_name
        self.icon = icon

    def build(self):
        fg, bg = tone(self.tone_name)
        children = []
        if self.icon:
            children.append(ft.Icon(self.icon, size=13, color=fg))
        children.append(ft.Text(self.text, size=11, weight=ft.FontWeight.W_600, color=fg))

        self.content = ft.Row(children, spacing=5, tight=True)
        self.padding = ft.Padding.symmetric(horizontal=10, vertical=5)
        self.bgcolor = bg
        self.border_radius = Radius.PILL
