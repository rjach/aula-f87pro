"""
Animated per-key lighting themes.

A theme is pure colour maths: given a key's physical position and how long the
effect has been running, it returns that key's colour. It knows nothing about
HID, packets or LED indices -- the device layer maps positions to LEDs. That
keeps themes trivially testable and previewable without hardware.
"""
import colorsys
import math
from typing import Dict, List, Tuple

from .layout import BOARD_WIDTH_UNITS, PIXEL_COLUMNS, physical_x, pixel_columns
from .simulation import ForgeTheme, SandfallTheme
# Re-exported: the contract and helpers used to live here, and callers still
# import them from this module.
from .theme_base import (  # noqa: F401
    KEYBOARD_COLUMNS,
    KEYBOARD_ROWS,
    RGB,
    Theme,
    _FULL_TURN,
    _MAX_CHANNEL,
    _lerp,
    _normalized_column,
    _normalized_row,
    _stable_jitter,
    flowing_position,
    hex_to_rgb,
    sample_palette,
    sample_ramp,
    scale_brightness,
)

class StaticTheme(Theme):
    """Base for themes whose output never changes, so they can render once."""

    frames_per_second = 1

    @property
    def is_static(self) -> bool:
        return True


# --------------------------------------------------------------------------
# Themes
# --------------------------------------------------------------------------

class AuroraTheme(Theme):
    """Northern-lights ribbons of teal, green and violet travelling sideways."""

    name = "aurora"
    description = "Northern-lights ribbons flowing key-to-key: teal, cyan, violet"
    frames_per_second = 30

    _PALETTE = [
        hex_to_rgb("#115e6b"),  # deep polar teal
        hex_to_rgb("#0ea5a4"),  # teal
        hex_to_rgb("#34d399"),  # mint green
        hex_to_rgb("#22d3ee"),  # cyan
        hex_to_rgb("#818cf8"),  # periwinkle
        hex_to_rgb("#7c3aed"),  # violet
        hex_to_rgb("#3730a3"),  # indigo night
    ]

    #: Ribbons visible across the board at once.
    _RIBBON_WAVELENGTH = 1.45
    #: Travel speed in key widths per second: fast enough to read clearly as
    #: motion, slow enough to sit behind the keystroke bubbles rather than
    #: compete with them.
    _KEYS_PER_SECOND = 3.2
    _SHIMMER_DEPTH = 0.30         # how strongly the curtain dims
    _ROW_SKEW = 0.085             # diagonal lean of the ribbons
    _FLOOR_BRIGHTNESS = 0.62      # keys never go fully dark

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        horizontal = _normalized_column(column)
        vertical = _normalized_row(row)

        # Ribbons lean diagonally and travel key-to-key across the board.
        gradient_position = flowing_position(
            row, column, elapsed,
            cycles=self._RIBBON_WAVELENGTH,
            row_lean=self._ROW_SKEW,
            keys_per_second=self._KEYS_PER_SECOND,
        )
        base = sample_palette(self._PALETTE, gradient_position)

        # The brightness wave rides the same travelling coordinate, so the whole
        # curtain translates as one image. Animating it independently would let
        # the shimmer slide against the colours and break the illusion that a
        # key is handing its colour to its neighbour.
        sway = math.sin(gradient_position * _FULL_TURN * 0.55 - vertical * 1.1)
        brightness = self._FLOOR_BRIGHTNESS + self._SHIMMER_DEPTH * (sway + 1) / 2

        # The top rows of a real aurora are brighter than its base.
        brightness += (1.0 - vertical) * 0.22

        return scale_brightness(base, brightness)


class NebulaTheme(Theme):
    """Deep-space magenta and indigo clouds with slow-drifting starlight."""

    name = "nebula"
    description = "Magenta and indigo clouds with drifting starlight"
    frames_per_second = 30

    _PALETTE = [
        hex_to_rgb("#1e1b4b"),
        hex_to_rgb("#4c1d95"),
        hex_to_rgb("#9333ea"),
        hex_to_rgb("#db2777"),
        hex_to_rgb("#f472b6"),
        hex_to_rgb("#312e81"),
    ]

    _CLOUD_SPEED = 0.04
    _STAR_SPEED = 1.7
    _STAR_DENSITY = 0.88          # jitter above this threshold twinkles
    _STAR_BOOST = 1.9
    _BASE_BRIGHTNESS = 0.68

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        horizontal = _normalized_column(column)
        vertical = _normalized_row(row)

        # Two offset sine fields give the clouds a non-repeating, billowy look.
        turbulence = (
            math.sin(horizontal * 3.1 + elapsed * 0.31)
            + math.sin(vertical * 2.3 - elapsed * 0.22)
        ) * 0.09

        base = sample_palette(
            self._PALETTE, horizontal * 0.9 + turbulence + elapsed * self._CLOUD_SPEED
        )
        brightness = self._BASE_BRIGHTNESS + 0.25 * (1.0 - vertical)

        # A handful of keys twinkle on their own phase.
        jitter = _stable_jitter(row, column)
        if jitter > self._STAR_DENSITY:
            twinkle = (math.sin(elapsed * self._STAR_SPEED + jitter * _FULL_TURN) + 1) / 2
            brightness += twinkle * self._STAR_BOOST * (jitter - self._STAR_DENSITY) * 8

        return scale_brightness(base, brightness)


class EmberTheme(Theme):
    """Warm coals glowing up from the spacebar row into cooling smoke."""

    name = "ember"
    description = "Warm coals rising from the bottom row into cooling smoke"
    frames_per_second = 30

    # Cool smoke at the top through to white-hot coals at the bottom.
    _HEAT_RAMP = [
        hex_to_rgb("#3b0764"),  # smoke, faint violet
        hex_to_rgb("#7f1d1d"),  # dark ember
        hex_to_rgb("#dc2626"),  # red
        hex_to_rgb("#f97316"),  # orange
        hex_to_rgb("#fbbf24"),  # amber
        hex_to_rgb("#fef3c7"),  # white-hot
    ]

    _FLICKER_SPEED = 2.3
    _FLICKER_DEPTH = 0.18
    _HEIGHT_FALLOFF = 0.95

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        # Heat is highest at the bottom of the board and fades upward.
        height_above_coals = _normalized_row(KEYBOARD_ROWS - 1 - row)
        heat = 1.0 - height_above_coals * self._HEIGHT_FALLOFF

        jitter = _stable_jitter(row, column)
        flicker = math.sin(elapsed * self._FLICKER_SPEED + jitter * _FULL_TURN)
        heat += flicker * self._FLICKER_DEPTH

        base = sample_ramp(self._HEAT_RAMP, heat)
        # Hotter keys also burn brighter, which keeps the coals reading as light
        # rather than as flat orange paint.
        return scale_brightness(base, 0.6 + max(0.0, min(1.0, heat)) * 0.4)


class TideTheme(Theme):
    """Cool ocean swell rolling across the board in deep blues and cyan."""

    name = "tide"
    description = "Ocean swell rolling across the board in deep blue and cyan"
    frames_per_second = 30

    _PALETTE = [
        hex_to_rgb("#0c4a6e"),
        hex_to_rgb("#0369a1"),
        hex_to_rgb("#0ea5e9"),
        hex_to_rgb("#22d3ee"),
        hex_to_rgb("#2dd4bf"),
        hex_to_rgb("#0e7490"),
    ]

    _SWELL_SPEED = 0.6
    _SWELL_WAVELENGTH = 1.1
    _FOAM_THRESHOLD = 0.82        # wave crests pick up white foam

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        horizontal = _normalized_column(column)
        vertical = _normalized_row(row)

        wave = math.sin(
            (horizontal * self._SWELL_WAVELENGTH - elapsed * 0.18) * _FULL_TURN
            + vertical * 0.9
        )
        crest = (wave + 1) / 2

        base = sample_palette(self._PALETTE, horizontal * 0.7 + elapsed * 0.03)
        brightness = 0.62 + crest * 0.38

        if crest > self._FOAM_THRESHOLD:
            foam = (crest - self._FOAM_THRESHOLD) / (1 - self._FOAM_THRESHOLD)
            base = tuple(int(_lerp(base[i], 255, foam * 0.35)) for i in range(3))

        return scale_brightness(base, brightness)


class SpectrumTheme(Theme):
    """A clean full-hue rainbow sweeping diagonally across the keys."""

    name = "spectrum"
    description = "Smooth full-hue rainbow sweeping diagonally"
    frames_per_second = 30

    _SWEEP_SPEED = 0.09
    _DIAGONAL_SPREAD = 0.75
    _ROW_SPREAD = 0.18
    _SATURATION = 0.95
    _VALUE = 0.9

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        hue = (
            _normalized_column(column) * self._DIAGONAL_SPREAD
            + _normalized_row(row) * self._ROW_SPREAD
            + elapsed * self._SWEEP_SPEED
        ) % 1.0
        red, green, blue = colorsys.hsv_to_rgb(hue, self._SATURATION, self._VALUE)
        return (int(red * _MAX_CHANNEL), int(green * _MAX_CHANNEL), int(blue * _MAX_CHANNEL))


class DuskTheme(StaticTheme):
    """A still, low-glare sunset gradient -- easy on the eyes while working."""

    name = "dusk"
    description = "Still sunset gradient, low glare, good for long sessions"

    _PALETTE = [
        hex_to_rgb("#1e1b4b"),
        hex_to_rgb("#4c1d95"),
        hex_to_rgb("#be185d"),
        hex_to_rgb("#ea580c"),
        hex_to_rgb("#f59e0b"),
    ]

    _DIM = 0.7

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        # Non-cyclic sweep: sample only the first 'stop_count-1' fraction of the
        # wrapping palette so the gradient runs violet -> amber without looping
        # back through violet at the right edge.
        span = (len(self._PALETTE) - 1) / len(self._PALETTE)
        position = _normalized_column(column) * span
        base = sample_palette(self._PALETTE, position)
        # Upper rows sit slightly brighter, like a real sky.
        return scale_brightness(base, self._DIM + (1.0 - _normalized_row(row)) * 0.25)



class FlowTheme(Theme):
    """
    Every key a distinct colour, with the whole pattern travelling sideways so
    each key inherits the colour its neighbour just had.

    The effect is a continuous spatial gradient shifted by time rather than a
    per-key animation: at any moment adjacent keys differ by a small, even hue
    step (distinct but coherent), and as time advances the gradient slides by
    exactly one key position per `_KEYS_PER_SECOND`.
    """

    name = "flow"
    description = "Distinct colour per key, flowing key-to-key across the board"
    frames_per_second = 30

    #: Rainbows visible across the board at once. Just over one keeps adjacent
    #: keys clearly different while neighbours stay closely related.
    _HUE_CYCLES = 1.15
    #: Diagonal lean, in hue-cycles per row, so the flow is not a flat column wipe.
    _ROW_LEAN = 0.09
    #: How fast the pattern travels, in key widths per second.
    _KEYS_PER_SECOND = 6.5
    _SATURATION = 0.92
    _VALUE = 1.0

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        hue = flowing_position(
            row, column, elapsed,
            cycles=self._HUE_CYCLES,
            row_lean=self._ROW_LEAN,
            keys_per_second=self._KEYS_PER_SECOND,
        ) % 1.0

        red, green, blue = colorsys.hsv_to_rgb(hue, self._SATURATION, self._VALUE)
        return (int(red * _MAX_CHANNEL), int(green * _MAX_CHANNEL), int(blue * _MAX_CHANNEL))


class FrozenTheme(StaticTheme):
    """
    Freezes an animated theme at one instant.

    Used as a still base layer for reactive effects: the colours stay put so
    each key keeps its own steady colour, and only the bubbles move.
    """

    def __init__(self, theme: Theme, phase: float = 0.0):
        """
        @param theme - The theme to sample.
        @param phase - The moment, in seconds, to freeze it at.
        """
        self._theme = theme
        self._phase = phase
        self.name = theme.name
        self.description = f"{theme.description} (still)"

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        return self._theme.color_at(row, column, self._phase)


class InfernoTheme(Theme):
    """Molten fire: deep coals below, white-hot tongues licking upward."""

    name = "inferno"
    description = "Molten fire, white-hot and turbulent, rising up the board"
    frames_per_second = 45

    _HEAT_RAMP = [
        hex_to_rgb("#3d0d04"),  # charred, but still glowing -- a fully
                                #: dark key reads as a broken LED, not as smoke
        hex_to_rgb("#8c1007"),  # deep coal
        hex_to_rgb("#e02207"),  # red
        hex_to_rgb("#ff6a00"),  # orange
        hex_to_rgb("#ffc400"),  # amber
        hex_to_rgb("#fff4c2"),  # white-hot
    ]

    _RISE_SPEED = 2.6          # how fast flame fronts climb, rows per second
    _TURBULENCE_SPEED = 3.4
    _TURBULENCE_DEPTH = 0.34
    _FLICKER_SPEED = 11.0      # fast enough to crackle rather than pulse
    _FLICKER_DEPTH = 0.13
    _HEIGHT_FALLOFF = 1.05
    _FLOOR = 0.24              # embers never fully die

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        height = _normalized_row(KEYBOARD_ROWS - 1 - row)
        heat = 1.0 - height * self._HEIGHT_FALLOFF

        # Two counter-moving waves make the flame front climb and churn rather
        # than pulse uniformly.
        churn = (
            math.sin(column * 0.9 - elapsed * self._RISE_SPEED + row * 1.3)
            + math.sin(column * 0.41 + elapsed * self._TURBULENCE_SPEED * 0.5)
        ) * 0.5
        heat += churn * self._TURBULENCE_DEPTH

        jitter = _stable_jitter(row, column)
        heat += math.sin(elapsed * self._FLICKER_SPEED + jitter * _FULL_TURN) * self._FLICKER_DEPTH

        heat = max(0.0, min(1.0, heat))
        base = sample_ramp(self._HEAT_RAMP, heat)
        return scale_brightness(base, self._FLOOR + heat * 0.84)


class SynthwaveTheme(Theme):
    """Neon magenta and cyan bands with a bright scan sweeping through them."""

    name = "synthwave"
    description = "Neon magenta and cyan bands with a bright scanning sweep"
    frames_per_second = 45

    _PALETTE = [
        hex_to_rgb("#2b0a5e"),  # deep violet
        hex_to_rgb("#ff2bd6"),  # neon magenta
        hex_to_rgb("#7b2ff7"),  # electric purple
        hex_to_rgb("#00e5ff"),  # neon cyan
        hex_to_rgb("#ff6ec7"),  # hot pink
        hex_to_rgb("#1b0740"),  # near-black violet
    ]

    _BANDS = 1.3
    _ROW_LEAN = 0.12
    _KEYS_PER_SECOND = 4.5
    _SCAN_SPEED = 0.55         # sweeps per second
    _SCAN_WIDTH = 0.1          # as a fraction of the board
    _SCAN_BOOST = 1.5
    _FLOOR = 0.5

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        position = flowing_position(
            row, column, elapsed,
            cycles=self._BANDS,
            row_lean=self._ROW_LEAN,
            keys_per_second=self._KEYS_PER_SECOND,
        )
        base = sample_palette(self._PALETTE, position)

        # A bright bar sweeping left to right, the way a scanline crosses a CRT.
        horizontal = _normalized_column(column)
        scan_centre = (elapsed * self._SCAN_SPEED) % 1.4 - 0.2
        distance = abs(horizontal - scan_centre)
        scan = math.exp(-(distance * distance) / (2 * self._SCAN_WIDTH ** 2))

        return scale_brightness(base, self._FLOOR + 0.4 + scan * self._SCAN_BOOST)


class MatrixTheme(Theme):
    """Green code rain: bright heads falling down the board, trails behind."""

    name = "matrix"
    description = "Green code rain falling down the board with bright heads"
    frames_per_second = 45

    _HEAD = hex_to_rgb("#d9ffe6")
    _BRIGHT = hex_to_rgb("#31ff7a")
    _MID = hex_to_rgb("#0f9c3f")
    _FLOOR_COLOR = hex_to_rgb("#04160a")

    _FALL_SPEED = 5.2          # rows per second, before per-column variation
    #: Spread of per-column fall speeds. Without this every column shares one
    #: period and the whole board repeats exactly, which reads as a looping
    #: texture rather than rain.
    _SPEED_SPREAD = 0.55
    _TRAIL_LENGTH = 4.2        # rows
    _HEAD_LENGTH = 0.7         # rows counted as the bright head
    #: Cycle longer than the board so gaps appear between drops.
    _CYCLE = 13.0

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        # Each column falls on its own offset and at its own speed, so the rain
        # is neither a solid bar nor a pattern that repeats as a whole.
        offset = _stable_jitter(0, column) * self._CYCLE
        speed = self._FALL_SPEED * (
            1.0 + (_stable_jitter(1, column) - 0.5) * self._SPEED_SPREAD
        )
        head_position = (elapsed * speed + offset) % self._CYCLE

        # Distance from this key up to the falling head.
        behind = head_position - row

        if behind < 0.0 or behind > self._TRAIL_LENGTH:
            return self._FLOOR_COLOR

        if behind <= self._HEAD_LENGTH:
            return self._HEAD

        decay = 1.0 - (behind - self._HEAD_LENGTH) / (self._TRAIL_LENGTH - self._HEAD_LENGTH)
        base = tuple(int(_lerp(self._MID[i], self._BRIGHT[i], decay)) for i in range(3))
        # Never fall below the resting glow, so no key looks dead.
        return tuple(max(self._FLOOR_COLOR[i], int(base[i] * (0.25 + decay * 0.75)))
                     for i in range(3))


class VoltageTheme(Theme):
    """Electric arcs cracking across a dark blue field."""

    name = "voltage"
    description = "Electric white-blue arcs cracking across a dark field"
    frames_per_second = 45

    _FIELD = hex_to_rgb("#04122e")
    _ARC = hex_to_rgb("#7fdcff")
    _CORE = hex_to_rgb("#ffffff")

    _ARC_COUNT = 3
    _ARC_SPEED = 1.9
    _ARC_WIDTH = 0.62          # in key widths
    _CRACKLE_SPEED = 17.0
    _GLOW = 0.30

    def _arc_column(self, index: int, row: int, elapsed: float) -> float:
        """Column this arc occupies at this row, zig-zagging as it descends."""
        phase = elapsed * self._ARC_SPEED + index * 2.1
        sweep = (math.sin(phase) * 0.5 + 0.5) * (KEYBOARD_COLUMNS - 1)
        # The lateral kink per row is what makes it read as a jagged arc
        # rather than a straight moving line.
        kink = math.sin(row * 2.4 + phase * 2.7 + index) * 1.9
        return sweep + kink

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        intensity = 0.0
        for index in range(self._ARC_COUNT):
            distance = abs(column - self._arc_column(index, row, elapsed))
            intensity += math.exp(
                -(distance * distance) / (2 * self._ARC_WIDTH * self._ARC_WIDTH)
            )

        # High-frequency crackle so the arcs flicker like real discharge.
        crackle = 0.75 + 0.25 * math.sin(
            elapsed * self._CRACKLE_SPEED + _stable_jitter(row, column) * _FULL_TURN
        )
        intensity = min(1.0, intensity * crackle)

        color = tuple(
            int(_lerp(self._FIELD[i], self._ARC[i], min(1.0, intensity * 1.4)))
            for i in range(3)
        )
        if intensity > 0.75:
            core = (intensity - 0.75) / 0.25
            color = tuple(int(_lerp(color[i], self._CORE[i], core)) for i in range(3))

        return scale_brightness(color, self._GLOW + 0.7 + intensity * 0.3)


class SupernovaTheme(Theme):
    """
    A spinning prismatic galaxy: spiral arms wheel around the centre of the
    board while shockwaves burst outward from a white-hot core.

    The only radial theme. It works in true physical key positions rather than
    column indices, otherwise the row stagger shears the rings into zig-zags.
    """

    name = "supernova"
    description = "Spinning prismatic galaxy with shockwaves bursting from a white-hot core"
    frames_per_second = 45

    _PALETTE = [
        hex_to_rgb("#ff1f8e"),  # hot magenta
        hex_to_rgb("#ff8a00"),  # solar orange
        hex_to_rgb("#ffe14d"),  # gold
        hex_to_rgb("#19f5c1"),  # plasma mint
        hex_to_rgb("#00b3ff"),  # electric blue
        hex_to_rgb("#8a2be2"),  # ultraviolet
    ]
    _WHITE = (255, 255, 255)

    _CENTER_X = BOARD_WIDTH_UNITS / 2
    _CENTER_ROW = (KEYBOARD_ROWS - 1) / 2
    #: The board is three times wider than tall; stretching the vertical axis
    #: lets rings reach the top and bottom rows before they run off the sides.
    _VERTICAL_STRETCH = 1.7

    _ARM_COUNT = 2
    _ARM_TWIST = 0.55          # radians of arm curl per key of radius
    _SPIN_SPEED = 2.4          # radians per second
    _ARM_DEPTH = 0.55          # how far the gaps between arms dim
    _FLOOR = 0.34              # gaps still glow, so no key looks dead
    _HUE_PER_KEY = 0.045       # colour drift outward along the radius
    _HUE_SPEED = 0.07          # palette cycles per second

    _SHOCK_SPEED = 7.5         # keys per second
    _SHOCK_PERIOD = 2.2        # seconds between bursts
    _SHOCK_WIDTH = 0.9         # keys
    _SHOCK_REACH = 11.0        # radius at which a shockwave has faded out

    _CORE_RADIUS = 1.5         # keys
    _CORE_PULSE_SPEED = _FULL_TURN / _SHOCK_PERIOD   # core flares with each burst

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        offset_x = physical_x(row, column) - self._CENTER_X
        offset_y = (row - self._CENTER_ROW) * self._VERTICAL_STRETCH
        radius = math.hypot(offset_x, offset_y)
        angle = math.atan2(offset_y, offset_x)

        # Hue follows the angle, so the whole colour wheel visibly rotates.
        hue_position = (
            angle / _FULL_TURN
            + radius * self._HUE_PER_KEY
            - elapsed * self._HUE_SPEED
        )
        base = sample_palette(self._PALETTE, hue_position)

        # Curling the arm phase with radius turns straight spokes into a spiral.
        arm = math.sin(
            self._ARM_COUNT * angle + radius * self._ARM_TWIST - elapsed * self._SPIN_SPEED
        )
        brightness = self._FLOOR + self._ARM_DEPTH * (arm + 1) / 2

        whiteness = self._shockwave(radius, elapsed) + self._core(radius, elapsed)
        whiteness = min(1.0, whiteness)
        color = tuple(int(_lerp(base[i], self._WHITE[i], whiteness)) for i in range(3))
        return scale_brightness(color, brightness + whiteness * 0.6)

    def _shockwave(self, radius: float, elapsed: float) -> float:
        """Strength of the expanding ring at this radius, fading as it travels."""
        ring_radius = (elapsed % self._SHOCK_PERIOD) * self._SHOCK_SPEED
        distance = radius - ring_radius
        ring = math.exp(-(distance * distance) / (2 * self._SHOCK_WIDTH ** 2))
        fade = max(0.0, 1.0 - ring_radius / self._SHOCK_REACH)
        return ring * fade * 0.85

    def _core(self, radius: float, elapsed: float) -> float:
        """White-hot centre that flares in time with each shockwave."""
        glow = math.exp(-(radius * radius) / (2 * self._CORE_RADIUS ** 2))
        pulse = 0.65 + 0.35 * math.cos(elapsed * self._CORE_PULSE_SPEED)
        return glow * pulse


# 5-row pixel font, variable width. '#' is a lit pixel.
_GLYPH_HEIGHT = 5
_GLYPHS: Dict[str, Tuple[str, ...]] = {
    "A": (".#.", "#.#", "###", "#.#", "#.#"),
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "##.", "#..", "###"),
    "F": ("###", "#..", "##.", "#..", "#.."),
    "G": (".###", "#...", "#.##", "#..#", ".###"),
    "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"),
    "J": ("..#", "..#", "..#", "#.#", ".#."),
    "K": ("#.#", "#.#", "##.", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "###"),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#"),
    "N": ("##.", "#.#", "#.#", "#.#", "#.#"),
    "O": (".#.", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "##.", "#..", "#.."),
    "Q": (".#..", "#.#.", "#.#.", "#.#.", ".###"),
    "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "S": (".##", "#..", ".#.", "..#", "##."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."),
    "U": ("#.#", "#.#", "#.#", "#.#", "###"),
    "V": ("#.#", "#.#", "#.#", "#.#", ".#."),
    "W": ("#...#", "#...#", "#.#.#", "##.##", "#...#"),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("###", "..#", ".#.", "#..", "###"),
    " ": ("..", "..", "..", "..", ".."),
}
_GLYPH_SPACING = 1
#: Glyphs whose left column is nearly empty and so serves as their own gap.
#: The board is only 18 pixels wide; this is what lets a five-letter word fit.
_SELF_SPACED_GLYPHS = frozenset("J")


def render_text_bitmap(text: str) -> List[List[bool]]:
    """
    Rasterise text into rows of pixels using the built-in 5-row font.

    @param text - Text to draw; case-insensitive, unknown characters are blank.
    @returns `_GLYPH_HEIGHT` rows of booleans, all the same length.
    """
    rows: List[List[bool]] = [[] for _ in range(_GLYPH_HEIGHT)]
    for index, character in enumerate(text.upper()):
        glyph = _GLYPHS.get(character, _GLYPHS[" "])
        needs_gap = index > 0 and character not in _SELF_SPACED_GLYPHS
        for row_index, glyph_row in enumerate(glyph):
            if needs_gap:
                rows[row_index].extend([False] * _GLYPH_SPACING)
            rows[row_index].extend(pixel == "#" for pixel in glyph_row)
    return rows


class NameplateTheme(StaticTheme):
    """
    A word written across the board in still pixel letters, on unlit keys.

    Nothing else is coloured, so under --reactive the keystroke bubbles are
    the only thing that moves. Subclasses only set `_TEXT`, which must fit the
    board's `PIXEL_COLUMNS`.
    """

    allows_dark_keys = True
    # The name is the whole picture, not a backdrop: keep it at full strength.
    reactive_base_brightness = 1.0

    _TEXT = ""

    _LETTER_RAMP = [
        hex_to_rgb("#00f0ff"),  # cyan
        hex_to_rgb("#7c4dff"),  # violet
        hex_to_rgb("#ff2bd6"),  # magenta
        hex_to_rgb("#ffb300"),  # amber
    ]
    _UNLIT: RGB = (0, 0, 0)

    def __init__(self):
        bitmap = render_text_bitmap(self._TEXT)
        text_width = len(bitmap[0])
        if text_width > PIXEL_COLUMNS:
            raise ValueError(
                f"'{self._TEXT}' needs {text_width} pixel columns but the board "
                f"has {PIXEL_COLUMNS}"
            )
        self._bitmap = bitmap
        self._left_margin = (PIXEL_COLUMNS - text_width) // 2

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        # The spacebar row's keys are too wide to act as pixels.
        if row >= _GLYPH_HEIGHT:
            return self._UNLIT
        if not any(self._is_lit(row, pixel) for pixel in pixel_columns(row, column)):
            return self._UNLIT
        return sample_ramp(self._LETTER_RAMP, physical_x(row, column) / BOARD_WIDTH_UNITS)

    def _is_lit(self, bitmap_row: int, pixel: int) -> bool:
        text_column = pixel - self._left_margin
        row_pixels = self._bitmap[bitmap_row]
        return 0 <= text_column < len(row_pixels) and row_pixels[text_column]


class RojanTheme(NameplateTheme):
    """ROJAN written across the keys; every other key stays unlit."""

    name = "rojan"
    description = "ROJAN in still neon pixel letters on an unlit board; pair with --reactive"
    _TEXT = "ROJAN"


class ReactorTheme(Theme):
    """
    A board that never sits still: fast plasma churning underneath while
    sparks go off on their own several times a second, each throwing a ring.

    The sparks are the theme typing on itself, so the board looks struck even
    when nobody is touching it. Under --reactive, real keystrokes throw
    board-wide shockwaves on top and whip the plasma faster and brighter.
    """

    name = "reactor"
    description = "Hyperactive plasma that sparks on its own and surges when you type"
    frames_per_second = 60

    reactive_base_brightness = 0.6
    reactive_bubble_lifetime = 0.7
    reactive_bubble_radius = 11.0      # a keystroke's wave crosses the whole board
    reactive_surge = 2.5

    _PLASMA = [
        hex_to_rgb("#1a00ff"),  # deep electric blue
        hex_to_rgb("#00d5ff"),  # cyan
        hex_to_rgb("#00ff9d"),  # plasma green
        hex_to_rgb("#b300ff"),  # violet
        hex_to_rgb("#ff0a78"),  # hot pink
    ]
    _SPARK_COLORS = [
        (255, 255, 255),
        hex_to_rgb("#fff04d"),
        hex_to_rgb("#6dfcff"),
        hex_to_rgb("#ff7ad9"),
    ]

    _PLASMA_BRIGHTNESS = 0.42          # kept low so sparks punch through it
    _PLASMA_DEPTH = 0.38

    _SPARK_INTERVAL = 0.16             # seconds between self-fired sparks
    _SPARK_LIFETIME = 0.75
    _SPARK_RADIUS = 5.0                # keys
    _SPARK_RING_WIDTH = 0.55
    _SPARK_FLASH_WIDTH = 0.7           # size of the initial pop at the origin

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        key_x = physical_x(row, column)
        color = self._plasma(key_x, row, elapsed)

        live_sparks = int(self._SPARK_LIFETIME / self._SPARK_INTERVAL) + 1
        newest = math.floor(elapsed / self._SPARK_INTERVAL)
        for spark in range(newest - live_sparks, newest + 1):
            if spark < 0:
                continue
            strength = self._spark_strength(spark, key_x, row, elapsed)
            if strength <= 0.0:
                continue
            tint = self._SPARK_COLORS[spark % len(self._SPARK_COLORS)]
            color = tuple(min(_MAX_CHANNEL, int(color[i] + tint[i] * strength))
                          for i in range(3))
        return color

    def _plasma(self, key_x: float, row: int, elapsed: float) -> RGB:
        """Interfering sine fields: fast, never repeating, always in motion."""
        field = (
            math.sin(key_x * 0.55 + elapsed * 2.9)
            + math.sin(row * 1.2 - elapsed * 2.2)
            + math.sin((key_x + row * 1.7) * 0.38 + elapsed * 1.6)
            + math.sin(math.hypot(key_x - 9.0 + 5.0 * math.sin(elapsed * 0.9),
                                  (row - 2.5) * 1.7) * 0.9 - elapsed * 3.4)
        ) / 4
        base = sample_palette(self._PLASMA, field * 0.75 + elapsed * 0.11)
        return scale_brightness(base, self._PLASMA_BRIGHTNESS + self._PLASMA_DEPTH * field)

    def _spark_strength(self, spark: int, key_x: float, row: int, elapsed: float) -> float:
        """Light one self-fired spark adds to a key: a pop, then a ring."""
        age = elapsed - spark * self._SPARK_INTERVAL
        progress = age / self._SPARK_LIFETIME
        if not 0.0 <= progress < 1.0:
            return 0.0

        # Hashing the spark number makes the 'random' strikes a pure function
        # of time, so frames agree with each other and previews are repeatable.
        origin_x = _stable_jitter(spark, 17) * BOARD_WIDTH_UNITS
        origin_row = _stable_jitter(spark, 91) * (KEYBOARD_ROWS - 1)
        distance = math.hypot(key_x - origin_x, row - origin_row)

        ring_offset = distance - self._SPARK_RADIUS * math.sqrt(progress)
        ring = math.exp(-(ring_offset * ring_offset) / (2 * self._SPARK_RING_WIDTH ** 2))
        flash = math.exp(-(distance * distance) / (2 * self._SPARK_FLASH_WIDTH ** 2))
        flash *= max(0.0, 1.0 - progress * 4)

        return (ring * (1.0 - progress) ** 1.5 + flash) * 0.95


_THEME_CLASSES = (
    FlowTheme,
    ForgeTheme,
    ReactorTheme,
    SandfallTheme,
    SupernovaTheme,
    RojanTheme,
    InfernoTheme,
    SynthwaveTheme,
    MatrixTheme,
    VoltageTheme,
    AuroraTheme,
    NebulaTheme,
    TideTheme,
    EmberTheme,
    SpectrumTheme,
    DuskTheme,
)

#: Theme name -> instance. Themes are stateless, so instances are shared.
THEMES: Dict[str, Theme] = {cls.name: cls() for cls in _THEME_CLASSES}

DEFAULT_THEME = FlowTheme.name


def get_theme(name: str) -> Theme:
    """
    Look up a theme by name.

    @param name - Theme name, case-insensitive.
    @returns The matching theme instance.
    @raises ValueError If no theme with that name is registered.
    """
    theme = THEMES.get(name.strip().lower())
    if theme is None:
        raise ValueError(
            f"Unknown theme '{name}'. Available themes: {', '.join(sorted(THEMES))}"
        )
    return theme


def is_static(theme: Theme) -> bool:
    """
    Whether a theme renders one unchanging frame.

    @param theme - The theme to inspect.
    @returns True when the theme's output is time-invariant.
    """
    return getattr(theme, "is_static", False)


class BrightnessAdjusted(Theme):
    """
    Decorator that uniformly dims another theme.

    Wrapping keeps brightness out of every individual theme's maths -- each
    theme stays responsible only for its own colours.
    """

    def __init__(self, theme: Theme, level: float):
        """
        @param theme - The theme to wrap.
        @param level - Multiplier in the 0.0-1.0 range.
        """
        self._theme = theme
        self._level = max(0.0, min(1.0, level))
        self.name = theme.name
        self.description = theme.description
        self.frames_per_second = theme.frames_per_second
        self.allows_dark_keys = theme.allows_dark_keys
        self.reactive_base_brightness = theme.reactive_base_brightness
        self.reactive_bubble_lifetime = theme.reactive_bubble_lifetime
        self.reactive_bubble_radius = theme.reactive_bubble_radius
        self.reactive_surge = theme.reactive_surge
        self.listens_to_audio = theme.listens_to_audio

    @property
    def is_static(self) -> bool:
        return is_static(self._theme)

    def on_key_press(self, row: int, column: int) -> None:
        self._theme.on_key_press(row, column)

    def on_audio_levels(self, levels) -> None:
        self._theme.on_audio_levels(levels)

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        return scale_brightness(self._theme.color_at(row, column, elapsed), self._level)
