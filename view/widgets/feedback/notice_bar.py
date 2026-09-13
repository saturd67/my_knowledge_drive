import flet as ft

from view.theme import Radius, Space, palette, tone
from view.widgets.buttons.icon_button import IconButton

TONE_ICONS = {
    "primary": ft.Icons.INFO_ROUNDED,
    "success": ft.Icons.CHECK_CIRCLE_ROUNDED,
    "warning": ft.Icons.WARNING_AMBER_ROUNDED,
    "danger": ft.Icons.ERROR_ROUNDED,
    "info": ft.Icons.INFO_ROUNDED,
    "neutral": ft.Icons.INFO_OUTLINED,
}


class NoticeBar(ft.Container):
    """Message banner a screen drops into its layout.

    Part of the layout rather than an overlay, so it never covers a control
    and it stays put until `on_hide` clears it - nothing times out.
    """

    def __init__(self, message, tone_name="neutral", on_hide=None):
        super().__init__()
        self.message = message
        self.tone_name = tone_name
        self.on_hide = on_hide

    def build(self):
        p = palette()
        fg, bg = tone(self.tone_name)

        dismiss = IconButton(ft.Icons.CLOSE_ROUNDED, "Dismiss", self.on_hide, self.tone_name)
        # An IconButton keeps a 40px tap target by default, which would set the
        # height of the bar on its own - trimming the padding below does nothing
        # until this is boxed in too.
        dismiss.icon_size = 16
        dismiss.width = 22
        dismiss.height = 22
        dismiss.padding = 0

        self.content = ft.Row(
            [
                ft.Icon(TONE_ICONS.get(self.tone_name, TONE_ICONS["neutral"]), size=16, color=fg),
                ft.Text(self.message, size=12, weight=ft.FontWeight.W_600,
                        color=p.text, expand=True),
                dismiss,
            ],
            spacing=Space.SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.padding = ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.XS)
        self.bgcolor = bg
        self.border = ft.Border.all(1, fg)
        self.border_radius = Radius.MD
