import flet as ft

from view.theme import palette

#: Label column width. Every labelled row uses it, so the labels down a card
#: line up and their values start on the same edge.
KEY_WIDTH = 170


class RowLabel(ft.Container):
    """The label cell of a labelled row - fixed width, muted text.

    Only the label. What sits beside it is the caller's business, so a
    read-only value, a text field and a dropdown can all share the column
    without a widget per combination.
    """

    def __init__(self, label, width=KEY_WIDTH):
        super().__init__()
        self.label = label
        self.width = width

    def build(self):
        self.content = ft.Text(self.label, size=12, color=palette().text_muted)
