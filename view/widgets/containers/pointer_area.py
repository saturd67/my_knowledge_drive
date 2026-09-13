import flet as ft


class PointerArea(ft.GestureDetector):
    """Everything the pointer does over a styled Container: cursor, tap, hover.

    Flet's `Container` has no `mouse_cursor` of its own - only
    `GestureDetector` does. But a Container that keeps its own `on_click` or
    `on_hover` puts its gesture and mouse regions *inside* this one, and the
    innermost region wins the cursor, so wrapping alone changes nothing. The
    click and the hover therefore both live here, and the Container this wraps
    is left as pure styling.

    `is_clickable=False` still wraps, but leaves the plain arrow and no
    handlers - for the tab or the rail icon you are already on, which is drawn
    as selected rather than as something to press.

    `hover_bgcolor` is optional: pass it for a row that lights up under the
    pointer, leave it off for one that only needs the cursor.
    """

    def __init__(self, content, is_clickable=True, on_click=None, hover_bgcolor=None):
        self.hover_bgcolor = hover_bgcolor if is_clickable else None
        # Read on the first hover, not here: a wrapped widget sets its own
        # bgcolor in build(), which has not run yet while this is constructed.
        self.base_bgcolor = None
        super().__init__(
            content=content,
            mouse_cursor=ft.MouseCursor.CLICK if is_clickable else ft.MouseCursor.BASIC,
            on_tap=on_click if is_clickable else None,
            on_enter=self._on_enter if self.hover_bgcolor else None,
            on_exit=self._on_exit if self.hover_bgcolor else None,
        )

    def _on_enter(self, _):
        self.base_bgcolor = self.content.bgcolor
        self.content.bgcolor = self.hover_bgcolor
        self.content.update()

    def _on_exit(self, _):
        self.content.bgcolor = self.base_bgcolor
        self.content.update()
