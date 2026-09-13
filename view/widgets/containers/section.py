import flet as ft

from view.theme import Space, palette
from view.widgets.containers.card import Card
from view.widgets.text.subtitle import Subtitle


class SectionCard(Card):
    """A titled card: heading row on top, arbitrary content below."""

    def __init__(self, title_text, subtitle_text=None, trailing=None, content=None,
                 fill=False, **kwargs):
        """`fill` stretches the content to whatever height the card is given,
        which is what a section whose content scrolls itself needs - the
        heading stays put and only the content moves."""
        head = [ft.Text(title_text, size=15, weight=ft.FontWeight.W_700, color=palette().text)]
        if subtitle_text:
            head.append(Subtitle(subtitle_text, size=12))

        header_row = ft.Row(
            [
                ft.Column(head, spacing=2, expand=True),
                trailing or ft.Container(),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        children = [header_row]
        if content is not None:
            children.append(ft.Container(content=content, padding=ft.Padding.only(top=Space.LG),
                                         expand=fill))

        super().__init__(ft.Column(children, spacing=0, expand=fill), **kwargs)
