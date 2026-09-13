import flet as ft

from view.theme import Radius, Space, palette

#: `border=None` is a card with no outline at all - a surface that runs to the
#: edge of whatever holds it - so the default cannot be None.
_OUTLINE = object()


class Card(ft.Container):
    """The base surface: bordered, rounded, filled with the surface colour.

    `border` overrides the outline, for a card that is flush against
    something and only needs a rule on the side that separates the two.
    """

    def __init__(self, content, padding=Space.XL, radius=Radius.LG, bgcolor=None,
                 border=_OUTLINE, **kwargs):
        p = palette()
        super().__init__(
            content=content,
            padding=padding,
            bgcolor=bgcolor or p.surface,
            border=ft.Border.all(1, p.border) if border is _OUTLINE else border,
            border_radius=radius,
            **kwargs,
        )
