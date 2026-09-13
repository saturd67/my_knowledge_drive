import flet as ft

from view.theme import Radius, Space, palette


class NavItem(ft.Container):
    """One row in the sidebar navigation: icon, label, selected pill.

    Styling only. The click and the hover highlight belong to the `PointerArea`
    this is wrapped in - a Container that handles its own click keeps the
    cursor from ever reaching the pointer.
    """

    def __init__(self, text, icon, selected_icon, is_selected):
        super().__init__()
        self.text = text
        self.icon = icon
        self.selected_icon = selected_icon
        self.is_selected = is_selected

    def build(self):
        p = palette()
        fg = p.primary if self.is_selected else p.text_muted

        self.content = ft.Row(
            [
                ft.Icon(self.selected_icon if self.is_selected else self.icon, size=18, color=fg),
                ft.Text(
                    self.text,
                    size=13,
                    weight=ft.FontWeight.W_600 if self.is_selected else ft.FontWeight.W_500,
                    color=p.text if self.is_selected else p.text_muted,
                ),
            ],
            spacing=Space.MD,
        )
        self.padding = ft.Padding.symmetric(horizontal=Space.MD, vertical=10)
        self.bgcolor = p.primary_soft if self.is_selected else "transparent"
        self.border_radius = Radius.MD
