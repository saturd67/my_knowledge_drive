"""The brand block, from the bare logo tile up to the sidebar header.

Three controls that only exist for each other: `BrandHeader` wraps `Brand`,
which wraps `BrandMark`. They are read together and change together - the
tile size, the name beside it and the height of the header are one design
decision split across three constructors - so they share a file.
"""

import flet as ft

from view.theme import Radius, Space, palette


class BrandMark(ft.Container):
    """Just the logo tile - for the rail, where there is no room for the name."""

    def build(self):
        p = palette()
        self.content = ft.Icon(ft.Icons.AUTO_AWESOME_MOSAIC_ROUNDED, size=20, color=p.on_primary)
        self.width = 36
        self.height = 36
        self.bgcolor = p.primary
        self.border_radius = Radius.MD
        self.alignment = ft.Alignment.CENTER


class Brand(ft.Row):
    """Logo tile with the product name and the portal underneath."""

    def __init__(self, portal="Admin Portal"):
        super().__init__()
        self.portal = portal

    def build(self):
        p = palette()
        self.controls = [
            BrandMark(),
            ft.Column(
                [
                    ft.Text("MyKnowledgeDrive", size=14, weight=ft.FontWeight.W_700,
                            color=p.text),
                    ft.Text(self.portal, size=11, color=p.text_faint),
                ],
                spacing=0,
                # Without this the column takes the full height of the row
                # and stacks the two lines from the top, which reads as the
                # name sitting high beside the logo in a fixed-height header.
                tight=True,
            ),
        ]
        self.spacing = Space.MD
        self.vertical_alignment = ft.CrossAxisAlignment.CENTER


class BrandHeader(ft.Container):
    """The block both portals open their sidebar with.

    One fixed height for the two of them, so the rule under the brand lands on
    the same line in either portal - and, in the user portal, on the same line
    as the rule under the file bar beside it.
    """

    HEIGHT = 60

    def __init__(self, portal):
        super().__init__()
        self.portal = portal

    def build(self):
        p = palette()
        self.content = Brand(portal=self.portal)
        self.height = self.HEIGHT
        self.padding = ft.Padding.symmetric(horizontal=Space.MD, vertical=0)
        self.border = ft.Border.only(bottom=ft.BorderSide(1, p.border))
