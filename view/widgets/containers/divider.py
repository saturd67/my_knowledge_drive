import flet as ft

from view.theme import Space, palette


class Divider(ft.Container):
    """A hairline rule with margin either side.

    Not `ft.Divider` - this one is a plain filled box, so its colour and the
    space around it come from the palette and the spacing scale.
    """

    def __init__(self, top=Space.LG, bottom=Space.LG):
        super().__init__()
        self.top_space = top
        self.bottom_space = bottom

    def build(self):
        self.height = 1
        self.bgcolor = palette().border_soft
        self.margin = ft.Margin.only(top=self.top_space, bottom=self.bottom_space)
