import flet as ft

from view.theme import Space, palette, tone
from view.widgets.containers.card import Card
from view.widgets.containers.icon_badge import IconBadge


class StatCard(Card):
    """Compact tile: badge on the left, figure and label stacked beside it."""

    def __init__(self, icon, caption, value, hint=None, tone_name="primary", expand=True):
        p = palette()
        fg, _ = tone(tone_name)

        label_row = [ft.Text(caption, size=11, weight=ft.FontWeight.W_600, color=p.text_muted)]
        if hint:
            label_row.append(ft.Text(hint, size=11, color=fg))

        super().__init__(
            ft.Row(
                [
                    IconBadge(icon, tone_name, size=34, icon_size=16),
                    ft.Column(
                        [
                            ft.Text(value, size=19, weight=ft.FontWeight.W_700, color=p.text),
                            ft.Row(label_row, spacing=Space.SM),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ],
                spacing=Space.MD,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=Space.MD,
            expand=expand,
        )
