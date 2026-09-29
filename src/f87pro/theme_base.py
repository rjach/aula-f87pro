"""
The theme contract and the colour maths every theme shares.

Kept apart from the theme catalogue so other kinds of theme (see
`simulation.py`) can build on the same contract without a circular import.
"""
import math
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

RGB = Tuple[int, int, int]

# Physical grid of the F87 Pro (TKL): 6 rows, 17 columns at the widest.
KEYBOARD_ROWS = 6
KEYBOARD_COLUMNS = 17

_MAX_CHANNEL = 255
_FULL_TURN = 2 * math.pi


# --------------------------------------------------------------------------
# Colour helpers
# --------------------------------------------------------------------------

def hex_to_rgb(hex_color: str) -> RGB:
    """
    Convert a '#rrggbb' string to an RGB tuple.

    @param hex_color - Hex colour, with or without the leading '#'.
    @returns The equivalent (r, g, b) tuple.
    """
    value = hex_color.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _lerp(start: float, end: float, position: float) -> float:
    """Linearly interpolate between two scalars."""
    return start + (end - start) * position


def sample_palette(palette: List[RGB], position: float) -> RGB:
    """
    Sample a colour from a cyclic gradient.

    The palette wraps, so position 0.0 and 1.0 return the same colour and an
    animation can drift through it forever without a visible seam.

    @param palette - Ordered gradient stops.
    @param position - Any real number; only its fractional part is used.
    @returns The interpolated colour at that point in the gradient.
    """
    stop_count = len(palette)
    scaled = (position % 1.0) * stop_count
    index = int(scaled)
    blend = scaled - index

    current = palette[index % stop_count]
    following = palette[(index + 1) % stop_count]

    return (
        int(_lerp(current[0], following[0], blend)),
        int(_lerp(current[1], following[1], blend)),
        int(_lerp(current[2], following[2], blend)),
    )


def sample_ramp(ramp: List[RGB], position: float) -> RGB:
    """
    Sample a colour from a non-cyclic gradient.

    Unlike `sample_palette` this does not wrap: position 0.0 is the first stop
    and 1.0 is the last, which is what a heat or sunset ramp needs.

    @param ramp - Ordered gradient stops, at least two.
    @param position - Clamped to the 0.0-1.0 range.
    @returns The interpolated colour.
    """
    clamped = max(0.0, min(1.0, position))
    segment_count = len(ramp) - 1
    scaled = clamped * segment_count
    index = min(int(scaled), segment_count - 1)
    blend = scaled - index

    current, following = ramp[index], ramp[index + 1]
    return (
        int(_lerp(current[0], following[0], blend)),
        int(_lerp(current[1], following[1], blend)),
        int(_lerp(current[2], following[2], blend)),
    )


def scale_brightness(color: RGB, factor: float) -> RGB:
    """
    Multiply a colour's intensity, clamped to the valid channel range.

    @param color - The base colour.
    @param factor - Multiplier; values above 1.0 are clamped per channel.
    @returns The scaled colour.
    """
    return (
        max(0, min(_MAX_CHANNEL, int(color[0] * factor))),
        max(0, min(_MAX_CHANNEL, int(color[1] * factor))),
        max(0, min(_MAX_CHANNEL, int(color[2] * factor))),
    )


def _stable_jitter(row: int, column: int) -> float:
    """
    Deterministic per-key offset in [0, 1).

    Themes use this instead of `random` so every frame of an animation agrees
    on which keys are 'ahead' -- random per frame would just look like noise.
    """
    seed = math.sin(row * 127.1 + column * 311.7) * 43758.5453
    return seed - math.floor(seed)


def flowing_position(row: int, column: int, elapsed: float, cycles: float,
                     row_lean: float, keys_per_second: float) -> float:
    """
    Position along a gradient that travels key-to-key across the board.

    Subtracting time makes the pattern move left-to-right: the value a key
    shows now is the value its left-hand neighbour showed a moment ago, which
    is what reads as colour flowing between keys.

    @param row - Physical row index.
    @param column - Physical column index.
    @param elapsed - Seconds since the effect started.
    @param cycles - Gradient repeats visible across the board at once.
    @param row_lean - Gradient offset per row, giving the flow a diagonal lean.
    @param keys_per_second - Travel speed, in key widths per second.
    @returns The gradient position, to be used cyclically.
    """
    step_per_key = cycles / (KEYBOARD_COLUMNS - 1)
    return (
        column * step_per_key
        + row * row_lean
        - elapsed * keys_per_second * step_per_key
    )


def _normalized_column(column: int) -> float:
    """Map a column index to the 0.0-1.0 range across the board."""
    return column / (KEYBOARD_COLUMNS - 1)


def _normalized_row(row: int) -> float:
    """Map a row index to the 0.0-1.0 range down the board."""
    return row / (KEYBOARD_ROWS - 1)


# --------------------------------------------------------------------------
# Theme contract
# --------------------------------------------------------------------------

class Theme(ABC):
    """A named, animated lighting pattern."""

    name: str = "unnamed"
    description: str = ""
    #: Frames per second this theme wants. Slower themes save USB bandwidth.
    frames_per_second: int = 30
    #: Whether unlit keys are part of the design. Off by default because a
    #: stray black key on a lit board reads as a broken LED.
    allows_dark_keys: bool = False

    # How the theme behaves as the backdrop under keystroke bubbles.
    #: Backdrop brightness, 0.0-1.0. None defers to the reactive default.
    reactive_base_brightness: Optional[float] = None
    #: Seconds one keystroke wave lives. None defers to the reactive default.
    reactive_bubble_lifetime: Optional[float] = None
    #: Final wave radius in key widths. None defers to the reactive default.
    reactive_bubble_radius: Optional[float] = None
    #: How hard typing drives the backdrop: at full typing energy the animation
    #: runs (1 + surge) times faster and brighter. 0 leaves it unaffected.
    reactive_surge: float = 0.0

    def on_key_press(self, row: int, column: int) -> None:
        """
        A key was pressed (only under --reactive). Most themes ignore this;
        simulation themes feed it into their world.

        May be called from the key-listener thread.

        @param row - Physical row of the pressed key.
        @param column - Physical column of the pressed key.
        """

    @abstractmethod
    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        """
        Colour for one key at one moment.

        @param row - Physical row index, 0 (function row) to 5 (spacebar row).
        @param column - Physical column index, 0 (left) to 16 (right).
        @param elapsed - Seconds since the effect started.
        @returns The key's (r, g, b) colour.
        """
