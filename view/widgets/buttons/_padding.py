import flet as ft

from view.theme import Space


def button_padding(is_dense):
    return ft.Padding.symmetric(
        horizontal=Space.LG if is_dense else Space.XL,
        vertical=Space.MD if is_dense else Space.LG,
    )
