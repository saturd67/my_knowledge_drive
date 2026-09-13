"""Putting text on the system clipboard from a click handler.

flet's clipboard is a Service and its `set` is a coroutine, so an `on_click` -
which is an ordinary function - cannot await it. `page.run_task` is what gets
a coroutine onto the event loop, the same way `page.run_thread` gets a
blocking function onto a worker thread.

The Clipboard is built per call rather than kept. That is flet's own
lifecycle: constructing one registers it with the page, and the registry
drops services again once nothing references them, so holding one would keep
a service alive for the life of the window to save an object allocation.

Every copy confirms itself. The button is a bare icon with no text, so
without the strip at the bottom of the window there is no way to tell a copy
that worked from one that silently did nothing.
"""

import flet as ft

from view.theme import Radius, Space, palette
from view.ui_thread import is_mounted

#: How long the confirmation stays up. Long enough to read, short enough that
#: it is gone before you reach for the next row.
CONFIRM_DURATION = 1800


def copy_to_clipboard(control, text, what):
    """Puts `text` on the clipboard and says what it copied.

    `what` names the value - "the folder id", "the run log" - because the
    confirmation appears at the bottom of the window, a long way from the
    button that was pressed.

    An empty value is reported rather than copied: quietly wiping the
    clipboard and claiming success is the one outcome that would be worse
    than the button doing nothing at all.
    """
    if not is_mounted(control):
        return

    page = control.page
    text = str(text or "")

    async def put_on_clipboard():
        if text:
            await ft.Clipboard().set(text)
        page.show_dialog(_confirmation(
            f"Copied {what}" if text else f"Nothing in {what} to copy",
            is_copied=bool(text),
        ))

    page.run_task(put_on_clipboard)


def _confirmation(message, is_copied):
    p = palette()
    return ft.SnackBar(
        content=ft.Row(
            [
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE_ROUNDED if is_copied
                    else ft.Icons.INFO_OUTLINE_ROUNDED,
                    size=16,
                    color=p.success if is_copied else p.text_muted,
                ),
                ft.Text(message, size=12, color=p.text),
            ],
            spacing=Space.SM,
            tight=True,
        ),
        bgcolor=p.surface,
        duration=CONFIRM_DURATION,
        behavior=ft.SnackBarBehavior.FLOATING,
        shape=ft.RoundedRectangleBorder(radius=Radius.MD),
        margin=Space.LG,
        width=320,
    )
