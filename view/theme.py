"""Design tokens and the Flet theme shared by both portals.

Light mode only - `palette()` returns the token set every control builds from.
"""

from dataclasses import dataclass

import flet as ft

FONT_FAMILY = "Segoe UI"
MONO_FONT_FAMILY = "Consolas"


class Space:
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32


class Radius:
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    PILL = 999


class Field:
    """One shape for every single-line text input in the portal.

    The Library filter and the reset confirmation box are the same control to
    look at, so they read their measurements from here rather than each
    carrying its own numbers and drifting apart.
    """

    WIDTH = 260
    HEIGHT = 40
    TEXT_SIZE = 12

    #: Horizontal inset for the text. Vertical is 0 - `dense` plus a fixed
    #: HEIGHT already centres the line, and padding on top of that pushes the
    #: text off centre.
    PADDING_X = Space.MD

    @classmethod
    def padding(cls):
        return ft.Padding.symmetric(horizontal=cls.PADDING_X, vertical=0)


class Window:
    """Shared geometry - both portals run in the same window."""
    WIDTH = 1280
    HEIGHT = 740
    MIN_WIDTH = 1040
    MIN_HEIGHT = 700


@dataclass(frozen=True)
class Palette:
    mode: str

    # Surfaces
    bg: str
    surface: str
    surface_alt: str
    surface_high: str
    sidebar: str

    # Lines
    border: str
    border_soft: str

    # Text
    text: str
    text_muted: str
    text_faint: str

    # Brand
    primary: str
    primary_soft: str
    on_primary: str

    # Status tones
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    info: str
    info_soft: str

    shadow: str


LIGHT = Palette(
    mode="light",
    bg="#F4F6FC",
    surface="#FFFFFF",
    surface_alt="#F7F9FD",
    surface_high="#EEF2FB",
    sidebar="#FFFFFF",
    border="#E1E7F2",
    border_soft="#EDF1F8",
    text="#131A2B",
    text_muted="#5D6880",
    text_faint="#8B95AC",
    primary="#3E5BD9",
    primary_soft="#E7ECFD",
    on_primary="#FFFFFF",
    success="#0E9F6E",
    success_soft="#DFF6ED",
    warning="#B4740A",
    warning_soft="#FBF0DA",
    danger="#D93B45",
    danger_soft="#FCE6E8",
    info="#0C7FA8",
    info_soft="#E1F2FA",
    shadow="#94A3B8",
)


def palette():
    return LIGHT


def tone(name):
    """Return (foreground, soft background) for a status tone."""
    p = palette()
    tones = {
        "primary": (p.primary, p.primary_soft),
        "success": (p.success, p.success_soft),
        "warning": (p.warning, p.warning_soft),
        "danger": (p.danger, p.danger_soft),
        "info": (p.info, p.info_soft),
        "neutral": (p.text_muted, p.surface_high),
    }
    return tones.get(name, tones["neutral"])


def build_theme(p):
    """Map the palette onto Flet's Material color scheme."""
    return ft.Theme(
        font_family=FONT_FAMILY,
        scaffold_bgcolor=p.bg,
        divider_color=p.border,
        color_scheme=ft.ColorScheme(
            primary=p.primary,
            on_primary=p.on_primary,
            primary_container=p.primary_soft,
            on_primary_container=p.primary,
            secondary=p.primary,
            on_secondary=p.on_primary,
            secondary_container=p.surface_high,
            on_secondary_container=p.text,
            tertiary=p.success,
            on_tertiary=p.on_primary,
            error=p.danger,
            on_error=p.on_primary,
            error_container=p.danger_soft,
            on_error_container=p.danger,
            surface=p.surface,
            on_surface=p.text,
            on_surface_variant=p.text_muted,
            surface_container=p.surface,
            surface_container_low=p.surface_alt,
            surface_container_lowest=p.bg,
            surface_container_high=p.surface_high,
            outline=p.border,
            outline_variant=p.border_soft,
            shadow=p.shadow,
            inverse_surface=p.text,
            on_inverse_surface=p.bg,
        ),
    )


def apply_window(page):
    """Size the window. Only on first launch - not when swapping portals."""
    page.window.width = Window.WIDTH
    page.window.height = Window.HEIGHT
    page.window.min_width = Window.MIN_WIDTH
    page.window.min_height = Window.MIN_HEIGHT


def apply(page):
    """Apply the palette to a page."""
    p = palette()
    page.theme = build_theme(p)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = p.bg
