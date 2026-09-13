import flet as ft

from view.theme import Radius, Space, palette, tone
from view.widgets.containers.pill import Pill

# Height of one step card in the horizontal pipeline list. Fixed so the cards
# agree along the bottom whatever their text runs to; the two Texts below are
# capped to match.
STEP_CARD_HEIGHT = 132

# And fixed width, because the pipeline scrolls sideways rather than dividing
# the window between however many steps there are. A card narrow enough to
# break "Step 4" across four lines is not a smaller card, it is an unreadable
# one - past a certain point the row has to run off the edge instead.
STEP_CARD_WIDTH = 240

#: status -> (icon, pill text, tone). `running` carries no icon: it gets a
#: spinner instead, which is a control rather than an icon name.
STEP_STATUSES = {
    "pending": (ft.Icons.RADIO_BUTTON_UNCHECKED_ROUNDED, "pending", "neutral"),
    "running": (None, "running", "primary"),
    "done": (ft.Icons.CHECK_CIRCLE_ROUNDED, "done", "success"),
    "failed": (ft.Icons.ERROR_ROUNDED, "failed", "danger"),
    "skipped": (ft.Icons.REMOVE_CIRCLE_OUTLINE_ROUNDED, "skipped", "neutral"),
}


class StepCard(ft.Container):
    """One step, as a column in the horizontal pipeline list.

    `status` is what a run moves: `pending` before it, `running` on it, then
    `done`, `failed`, or `skipped` for the steps a stopped run never reached.
    """

    def __init__(self, index, name, description, status="pending"):
        super().__init__()
        self.index = index
        self.name = name
        self.description = description
        self.status = status

    def build(self):
        p = palette()
        icon, pill_text, tone_name = STEP_STATUSES.get(self.status, STEP_STATUSES["pending"])
        fg, _ = tone(tone_name)

        # The step being worked on gets a spinner where the rest get an icon.
        leading = (
            ft.ProgressRing(width=16, height=16, stroke_width=2, color=fg)
            if icon is None
            else ft.Icon(icon, size=18, color=fg)
        )

        self.content = ft.Column(
            [
                ft.Row(
                    [
                        leading,
                        ft.Text(f"Step {self.index + 1}", size=11,
                                weight=ft.FontWeight.W_700, color=fg, expand=True),
                        Pill(pill_text, tone_name),
                    ],
                    spacing=Space.SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=Space.XS),
                ft.Text(self.name, size=13, weight=ft.FontWeight.W_600, color=p.text,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(self.description, size=11, color=p.text_muted,
                        max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
            ],
            spacing=2,
        )
        self.padding = Space.MD
        self.width = STEP_CARD_WIDTH
        self.height = STEP_CARD_HEIGHT
        self.bgcolor = p.surface_alt
        self.border = ft.Border.all(1, p.border_soft)
        self.border_radius = Radius.MD
