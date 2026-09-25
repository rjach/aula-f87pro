"""
Terminal preview of a theme.

Renders the real key layout using 24-bit ANSI colour so a theme can be judged
(and regression-checked) without the keyboard attached -- which also matters on
macOS, where opening the device needs a one-time permission grant.
"""
import os
import sys
import time
from typing import Optional

from .layout import KEY_LABELS, ROWS, KEY_POSITIONS
from .themes import RGB, Theme, is_static

_CELL_WIDTH = 5
_ESCAPE_RESET = "\x1b[0m"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"
_CURSOR_HOME = "\x1b[H"
_CLEAR_SCREEN = "\x1b[2J"

# Below this perceived luminance, white text reads better than black.
_DARK_BACKGROUND_LUMINANCE = 140


def supports_truecolor() -> bool:
    """
    Whether the terminal advertises 24-bit colour support.

    @returns True when truecolor output is expected to render correctly.
    """
    return os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


def _perceived_luminance(color: RGB) -> float:
    """Rec. 601 luma, used to pick a readable label colour."""
    red, green, blue = color
    return 0.299 * red + 0.587 * green + 0.114 * blue


def _cell(color: RGB, label: str) -> str:
    """Render one key as a coloured, labelled cell."""
    red, green, blue = color
    text = "255;255;255" if _perceived_luminance(color) < _DARK_BACKGROUND_LUMINANCE else "0;0;0"
    padded = label[: _CELL_WIDTH - 1].center(_CELL_WIDTH - 1)
    return f"\x1b[48;2;{red};{green};{blue}m\x1b[38;2;{text}m{padded}{_ESCAPE_RESET}"


def render_frame(theme: Theme, elapsed: float) -> str:
    """
    Build one full-keyboard frame as a printable string.

    @param theme - The theme to sample.
    @param elapsed - Seconds since the effect started.
    @returns The rendered frame, one terminal line per keyboard row.
    """
    lines = []
    for led_indices in ROWS:
        cells = []
        for led in led_indices:
            row, column = KEY_POSITIONS[led]
            cells.append(_cell(theme.color_at(row, column, elapsed), KEY_LABELS.get(led, "")))
        lines.append(" ".join(cells))
    return "\n".join(lines)


def preview(theme: Theme, duration: float = 8.0, fps: Optional[int] = None) -> None:
    """
    Animate a theme in the terminal.

    @param theme - The theme to preview.
    @param duration - Seconds to run; 0 runs until interrupted.
    @param fps - Frame rate override; defaults to the theme's own rate.
    """
    if not supports_truecolor():
        print("Note: $COLORTERM does not advertise truecolor; colours may be approximate.\n")

    frame_rate = fps or theme.frames_per_second
    frame_interval = 1.0 / frame_rate
    header = f"  {theme.name} - {theme.description}"

    if is_static(theme):
        print(header + "\n")
        print(render_frame(theme, 0.0))
        return

    sys.stdout.write(_HIDE_CURSOR + _CLEAR_SCREEN)
    start = time.time()
    try:
        while True:
            elapsed = time.time() - start
            if duration and elapsed >= duration:
                break
            sys.stdout.write(_CURSOR_HOME + header + "\n\n" + render_frame(theme, elapsed) + "\n")
            sys.stdout.flush()
            time.sleep(frame_interval)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(_SHOW_CURSOR + _ESCAPE_RESET + "\n")
        sys.stdout.flush()
