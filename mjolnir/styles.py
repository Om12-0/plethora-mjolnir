"""Design tokens (colours, geometry) and the application-wide Qt stylesheet."""
from __future__ import annotations

from string import Template

# --- palette ----------------------------------------------------------------
BG = "#161618"
BORDER = "#2A2A2E"
INPUT_BG = "#1C1C1F"
FG = "#ECECEC"
FG_MUTED = "#8A8A93"
ACCENT = "rgba(99,102,241,0.18)"
ACCENT_BORDER = "rgba(99,102,241,0.5)"
ACCENT_SOLID = "#6366F1"
WARNING = "#FBBF24"

SHADOW = dict(blur=28, dx=0, dy=8, alpha=115)

# --- capsules / pills (inspector badges) ------------------------------------
BADGE_BG = "rgba(255,255,255,0.06)"
BADGE_FG = FG
BADGE_BORDER = BORDER
BADGE_ACCENT_BG = ACCENT
BADGE_ACCENT_FG = "#C7D2FE"

CAPSULE_HEIGHT = 22
CAPSULE_RADIUS = CAPSULE_HEIGHT // 2
NUM_BADGE_SIZE = 16

# --- tray icon --------------------------------------------------------------
ICON_GRADIENT: tuple[str, str] = ("#5AC8FA", "#A78BFA")
ICON_FG = "#0B0F17"
ICON_SIZE = 64

# --- geometry ---------------------------------------------------------------
RADIUS = 12
CONTROL_RADIUS = 6
SCROLLBAR_WIDTH = 8
SEARCH_FONT_SIZE = 17

FONT_STACK = '"Segoe UI Variable", "Segoe UI", Inter'
MONO_STACK = '"Cascadia Mono", "Consolas", monospace'


def _muted(fg: str, rgb: str, alpha: float = 0.16) -> tuple[str, str]:
    r, g, b = (int(part) for part in rgb.split(","))
    return fg, f"rgba({r},{g},{b},{alpha})"


CATEGORY_COLORS: dict[str, tuple[str, str]] = {
    "PDF":   _muted("#F87171", "248,113,113"),
    "PY":    _muted("#7DD3FC", "56,189,248"),
    "SQL":   _muted("#34D399", "52,211,153"),
    "DOCX":  _muted("#60A5FA", "96,165,250"),
    "TXT":   _muted("#A1A1AA", "161,161,170", 0.14),
    "MD":    _muted("#C4B5FD", "167,139,250"),
    "JS":    _muted("#FDE68A", "250,204,21"),
    "TS":    _muted("#93C5FD", "59,130,246"),
    "HTML":  _muted("#FDBA74", "251,146,60"),
    "CSS":   _muted("#67E8F9", "34,211,238"),
    "JSON":  _muted("#FCA5A5", "239,68,68", 0.14),
    "CSV":   _muted("#6EE7B7", "16,185,129"),
    "TEX":   _muted("#D8B4FE", "192,132,252"),
    "SH":    _muted("#BBF7D0", "74,222,128"),
    "PS1":   _muted("#A5B4FC", "129,140,248"),
    "IPYNB": _muted("#FB923C", "249,115,22"),
    "OTHER": _muted(FG_MUTED, "138,138,147", 0.14),
}

_QSS = """/* PLETHORA MJOLNIR Stylesheet */
#mjRoot { background: transparent; }
#mjSurface, #panel { background: $bg; border: 1px solid $border; border-radius: ${radius}px; }
#mjTitleBar { background: transparent; border: none; }
#mjBrand { color: $fg_muted; font-family: $mono; font-size: 10px; }
#mjSeparator, #separator { background: $border; border: none; max-height: 1px; min-height: 1px; }

#searchArea, #inputArea { background: $input_bg; border: 1px solid $border; border-radius: ${radius}px; }
#searchArea[focused="true"], #inputArea[focused="true"] { border: 1px solid $accent_border; }
#search {
    background: transparent; border: none; border-radius: 0px;
    padding: 11px 4px 11px 4px; margin: 0px; color: $fg; font-family: $font;
    font-size: ${search_size}px; font-weight: 400; selection-background-color: $accent_solid;
    selection-color: #FFFFFF; placeholder-text-color: $fg_muted;
}
#searchIcon { color: $fg_muted; font-size: ${search_size}px; padding: 0px 2px 0px 10px; background: transparent; }

#results, #resultList { background: transparent; border: none; outline: 0; padding: 2px; }
#results::item, #resultList::item {
    color: $fg; background: transparent; border: 1px solid transparent;
    border-radius: ${radius}px; padding: 6px 8px;
}
#results::item:hover, #resultList::item:hover { background: $input_bg; }
#results::item:selected, #resultList::item:selected { background: $accent; border: 1px solid $accent_border; color: $fg; }
#results::item:disabled, #resultList::item:disabled { color: $fg_muted; }
#results QScrollBar, #resultList QScrollBar, #preview QScrollBar { background: transparent; }

#resultItem { background: transparent; border: 1px solid transparent; border-radius: ${radius}px; }
#resultItem:hover { background: $input_bg; }
#resultItem[selected="true"] { background: $accent; border: 1px solid $accent_border; }
#resultName { color: $fg; font-size: 14px; font-weight: 600; background: transparent; }
#resultPath { color: $fg_muted; font-size: 11px; background: transparent; }
#resultScore { color: $fg_muted; font-family: $mono; font-size: 10px; background: transparent; }
#emptyState { color: $fg_muted; font-size: 12px; padding: 18px 12px; background: transparent; }

#chip, #tag {
    background: $input_bg; color: $fg_muted; border: 1px solid $border;
    border-radius: ${control_radius}px; padding: 1px 7px; font-size: 10px; font-weight: 600; font-family: $mono;
}
#pill {
    background: $input_bg; color: $accent_solid; border: 1px solid $border;
    border-radius: ${control_radius}px; padding: 1px 7px; font-size: 10px; font-family: $mono;
}
#keycap {
    background: #232327; color: $fg; border: 1px solid $border; border-radius: 5px;
    padding: 2px 7px; font-size: 10px; font-family: $mono;
}
#keycapLabel, #keyLabel { color: $fg_muted; font-size: 11px; background: transparent; }
#keycaps { background: transparent; }

#inspector { background: $input_bg; border: 1px solid $border; border-radius: ${radius}px; }
#inspectorHeader { color: $fg_muted; font-family: $mono; font-size: 10px; padding: 8px 12px 0px 12px; background: transparent; }
#preview, #previewBox {
    background: transparent; border: none; border-radius: ${radius}px; padding: 10px 12px;
    color: $fg; font-size: 12px; selection-background-color: $accent_solid; selection-color: #FFFFFF;
}
#preview a, #previewBox a { color: $accent_solid; text-decoration: none; }
#previewMeta { color: $fg_muted; font-family: $mono; font-size: 10px; background: transparent; }

#footer, #statusBar { background: transparent; border-top: 1px solid $border; }
#status, #statusLabel { color: $fg_muted; font-size: 11px; padding: 4px 6px; background: transparent; }
#hint, #hintLabel { color: $fg_muted; font-size: 11px; padding: 0px 6px 4px 6px; background: transparent; }
#warning { color: $warning; font-size: 11px; background: transparent; }

#capsuleRow { background: transparent; }
#capsule, #capsuleAccent {
    background: $badge_bg; color: $badge_fg; border: 1px solid $badge_border;
    border-radius: ${capsule_radius}px; padding: 0px 9px; font-size: 10px; font-weight: 600; font-family: $mono;
}
#capsuleAccent { background: $badge_accent_bg; color: $badge_accent_fg; }
#numBadge {
    background: $badge_bg; color: $badge_fg; border: 1px solid $badge_border;
    border-radius: 4px; padding: 0px; font-family: $mono; font-size: 9px; font-weight: 700;
}

#actionPanel, #clipboardPanel { background: $input_bg; border: 1px solid $border; border-radius: ${radius}px; }
#actionHeader { background: transparent; }
#actionFileName { color: $fg; font-size: 14px; font-weight: 600; background: transparent; }
#actionFilePath { color: $fg_muted; font-size: 11px; background: transparent; }
#actionHint { color: $fg_muted; font-family: $mono; font-size: 10px; background: transparent; }
#actionRow { background: transparent; border: 1px solid transparent; border-radius: ${control_radius}px; }
#actionRow:hover { background: $bg; }
#actionRow[selected="true"] { background: $accent; border: 1px solid $accent_border; }
#actionKey {
    background: $bg; color: $fg; border: 1px solid $border; border-radius: 4px;
    padding: 1px 5px; font-family: $mono; font-size: 10px; font-weight: 700;
}
#actionRow[selected="true"] #actionKey { background: $accent_solid; color: #FFFFFF; border: 1px solid $accent_border; }
#actionGlyph { color: $fg_muted; font-size: 13px; background: transparent; }
#actionTitle { color: $fg; font-size: 12px; font-weight: 600; background: transparent; }
#actionDetail { color: $fg_muted; font-family: $mono; font-size: 10px; background: transparent; }
#emptyState2 { color: $fg_muted; font-size: 12px; padding: 14px 12px; background: transparent; }

#calcResult { color: $fg; font-family: $mono; font-size: 26px; font-weight: 600; background: transparent; }
#calcExpression, #modeCommand { color: $fg_muted; font-family: $mono; font-size: 12px; background: transparent; }
#modeTitle { color: $fg; font-size: 14px; font-weight: 600; background: transparent; }
#modeMeta { color: $fg_muted; font-family: $mono; font-size: 10px; background: transparent; }

QMenu { background: $bg; border: 1px solid $border; border-radius: ${radius}px; padding: 6px; color: $fg; font-family: $font; font-size: 12px; }
QMenu::item { background: transparent; border-radius: ${control_radius}px; padding: 6px 22px 6px 12px; }
QMenu::item:selected { background: $accent; color: $fg; }
QMenu::item:disabled { color: $fg_muted; }
QMenu::separator { background: $border; height: 1px; margin: 5px 8px; }
QToolTip {
    background: $bg; color: $fg; border: 1px solid $border;
    border-radius: ${control_radius}px; padding: 4px 7px; font-family: $font; font-size: 11px;
}

QScrollBar:vertical { background: transparent; width: ${sb}px; margin: 2px 0px 2px 0px; border: none; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #3A3A40; }
QScrollBar:horizontal { background: transparent; height: ${sb}px; margin: 0px 2px 0px 2px; border: none; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: #3A3A40; }
QScrollBar::add-line, QScrollBar::sub-line { background: transparent; border: none; width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar::up-arrow, QScrollBar::down-arrow, QScrollBar::left-arrow, QScrollBar::right-arrow {
    background: transparent; border: none; width: 0px; height: 0px;
}
"""

PANEL_QSS: str = Template(_QSS).substitute(
    bg=BG,
    border=BORDER,
    input_bg=INPUT_BG,
    fg=FG,
    fg_muted=FG_MUTED,
    accent=ACCENT,
    accent_border=ACCENT_BORDER,
    accent_solid=ACCENT_SOLID,
    warning=WARNING,
    badge_bg=BADGE_BG,
    badge_fg=BADGE_FG,
    badge_border=BADGE_BORDER,
    badge_accent_bg=BADGE_ACCENT_BG,
    badge_accent_fg=BADGE_ACCENT_FG,
    capsule_radius=CAPSULE_RADIUS,
    radius=RADIUS,
    control_radius=CONTROL_RADIUS,
    search_size=SEARCH_FONT_SIZE,
    sb=SCROLLBAR_WIDTH,
    font=FONT_STACK,
    mono=MONO_STACK,
)


def category_color(category: str) -> tuple[str, str]:
    return CATEGORY_COLORS.get((category or "OTHER").upper(), CATEGORY_COLORS["OTHER"])


def chip_qss(category: str) -> str:
    fg, bg = category_color(category)
    return (f"background: {bg}; color: {fg}; border: 1px solid {bg};"
            f" border-radius: {CONTROL_RADIUS}px; padding: 1px 7px;"
            f" font-family: {MONO_STACK}; font-size: 10px; font-weight: 600;")


def icon_palette(theme=None) -> dict:
    data = theme if isinstance(theme, dict) else {}
    gradient = data.get("icon_gradient")
    if isinstance(gradient, (list, tuple)) and len(gradient) >= 2:
        start, end = gradient[0], gradient[1]
    else:
        start = data.get("accent_solid") or ICON_GRADIENT[0]
        end = ICON_GRADIENT[1]
    fg = data.get("icon_fg") or data.get("bg") or ICON_FG
    return {"start": str(start), "end": str(end), "fg": str(fg)}


def capsule_qss(variant: str = "neutral") -> str:
    if str(variant).lower() == "accent":
        bg, fg = BADGE_ACCENT_BG, BADGE_ACCENT_FG
    else:
        bg, fg = BADGE_BG, BADGE_FG
    return (f"background: {bg}; color: {fg}; border: 1px solid {BADGE_BORDER};"
            f" border-radius: {CAPSULE_RADIUS}px; padding: 0px 9px;"
            f" font-family: {MONO_STACK}; font-size: 10px; font-weight: 600;")


def num_badge_qss() -> str:
    return (f"background: {BADGE_BG}; color: {BADGE_FG};"
            f" border: 1px solid {BADGE_BORDER}; border-radius: 4px;"
            f" padding: 0px; font-family: {MONO_STACK}; font-size: 9px;"
            f" font-weight: 700;")


def icon_signature(theme=None) -> tuple[str, str, str]:
    pal = icon_palette(theme)
    return (pal["start"], pal["end"], pal["fg"])
