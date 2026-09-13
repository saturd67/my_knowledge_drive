import flet as ft

from view.theme import palette


class Subtitle(ft.Text):

    def __init__(self, value, size=13):
        super().__init__(value, size=size, color=palette().text_muted)
