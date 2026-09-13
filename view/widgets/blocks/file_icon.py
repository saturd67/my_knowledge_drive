import flet as ft

from view.widgets.containers.icon_badge import IconBadge


class FileIcon(IconBadge):
    """Icon badge for a converted source file, keyed by its original type."""

    KINDS = {
        "doc": (ft.Icons.DESCRIPTION_ROUNDED, "info"),
        "image": (ft.Icons.IMAGE_ROUNDED, "warning"),
        "code": (ft.Icons.CODE_ROUNDED, "success"),
        "text": (ft.Icons.ARTICLE_ROUNDED, "neutral"),
    }

    def __init__(self, kind, size=38):
        icon, tone_name = self.KINDS.get(kind, self.KINDS["text"])
        super().__init__(icon, tone_name, size=size, icon_size=int(size * 0.48))
