"""Sending a control update from a worker thread.

`control.update()` is only safe on the thread running flet's event loop. It
ends up at `Connection.send_message`, which does `put_nowait` on an
`asyncio.Queue` (flet/messaging/flet_socket_server.py) - and `put_nowait` from
another thread appends the bytes without waking the loop, so the patch sits in
the queue unsent. The symptom is a screen that does not move while a
`page.run_thread` worker is running, then jumps to the current state the
moment anything else wakes the loop - resizing or minimising the window.

`call_soon_threadsafe` is the wake-up. It is what `Page.run_thread` itself
uses to get onto the loop in the first place (flet/controls/page.py).
"""

import asyncio


def is_mounted(control):
    """Whether `control` is on a page.

    `Control.page` raises when it is not, rather than returning None
    (flet/controls/base_control.py), and a background worker must not be
    brought down by drawing into a screen that has gone away.
    """
    try:
        return control.page is not None
    except RuntimeError:
        return False


def control_update(control):
    """Update `control` on the event loop thread, from wherever this is called.

    A no-op for a control that is not on the page. That is not an error: the
    screen may have been navigated away from, or the control may have just
    been built and its mount patch not sent yet - and in that case the patch
    that mounts it carries the current state anyway.
    """

    def update_on_loop():
        # Re-checked here: between scheduling this and it running, a redraw
        # may have replaced `control` with a freshly built one.
        if is_mounted(control):
            control.update()

    if not is_mounted(control):
        return

    loop = control.page.loop
    try:
        is_on_loop = asyncio.get_running_loop() is loop
    except RuntimeError:
        is_on_loop = False

    if is_on_loop:
        # A click handler, already where updates are allowed to be sent. Send
        # it now: deferring would leave the tree unbuilt for a tick, and
        # callers on this thread read it straight back.
        control.update()
        return

    loop.call_soon_threadsafe(update_on_loop)
