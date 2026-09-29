"""
Stateful simulation themes.

Every theme in `themes.py` is a pure function of key position and time. A
simulation theme is a different kind of thing: it owns a small world that is
stepped forward at a fixed rate, and key presses are inputs into that world
rather than decorations painted over it. What the board shows now depends on
everything that happened before.

The frame loop still only ever calls `color_at(row, column, elapsed)`, so the
world is advanced lazily: the first call at a new `elapsed` catches the
simulation up, and every other key in that frame reads the same state.
"""
import math
import random
import threading
from abc import abstractmethod
from typing import List, Optional, Tuple

from .layout import PIXEL_COLUMNS, physical_x, pixel_columns
from .theme_base import (
    KEYBOARD_ROWS,
    RGB,
    Theme,
    hex_to_rgb,
    sample_ramp,
    scale_brightness,
)

_WHITE: RGB = (255, 255, 255)


def _mix(start: RGB, end: RGB, amount: float) -> RGB:
    """Blend two colours; `amount` 0.0 is `start`, 1.0 is `end`."""
    clamped = max(0.0, min(1.0, amount))
    return (
        int(start[0] + (end[0] - start[0]) * clamped),
        int(start[1] + (end[1] - start[1]) * clamped),
        int(start[2] + (end[2] - start[2]) * clamped),
    )


#: Keys much wider than the text grid's nearest-key rule allows for, as
#: (row, column) -> width in key units. The pixel grid was built for lettering
#: on the upper rows and leaves most of the spacebar unowned, which would hide
#: sand resting right under its LED.
_WIDE_KEYS = {(5, 3): 6.25}


def _key_pixels(row: int, column: int) -> Tuple[int, ...]:
    """
    Simulation columns a key displays.

    Most keys own one or more cells of the shared pixel grid. A few are
    squeezed out by closer neighbours; they show the cell under their centre
    so no key is left without a view into the world.
    """
    width = _WIDE_KEYS.get((row, column))
    if width is not None:
        center = physical_x(row, column)
        return tuple(pixel for pixel in range(PIXEL_COLUMNS)
                     if abs(pixel + 0.5 - center) <= width / 2)
    owned = pixel_columns(row, column)
    if owned:
        return owned
    return (max(0, min(PIXEL_COLUMNS - 1, int(physical_x(row, column)))),)


class SimulationTheme(Theme):
    """
    Base for themes driven by a stepped, stateful world.

    Subclasses implement `_reset`, `_step` and `_render_key`. This class owns
    the clock: fixed-size steps (so behaviour does not depend on frame rate),
    a cap on catch-up work after a long gap, and a reset when time runs
    backwards, which happens whenever a fresh run or preview starts at 0.
    """

    #: Seconds per simulation step.
    step_seconds: float = 1 / 12
    #: The most simulated time replayed in one catch-up. Beyond this the world
    #: skips ahead rather than stalling the frame to replay every step.
    max_catch_up_seconds: float = 3.0

    def __init__(self):
        self._press_lock = threading.Lock()
        self._pending_presses: List[Tuple[int, int]] = []
        self._restart()

    def _restart(self) -> None:
        self._simulated_until = 0.0
        self._last_elapsed = 0.0
        self._reset()

    def on_key_press(self, row: int, column: int) -> None:
        # Called from the key-listener thread; applied on the next step.
        with self._press_lock:
            self._pending_presses.append((row, column))

    def color_at(self, row: int, column: int, elapsed: float) -> RGB:
        self._advance_to(elapsed)
        return self._render_key(row, column, elapsed)

    def _advance_to(self, elapsed: float) -> None:
        if elapsed < self._last_elapsed:
            self._restart()
        self._last_elapsed = elapsed

        if elapsed - self._simulated_until > self.max_catch_up_seconds:
            self._simulated_until = elapsed - self.max_catch_up_seconds

        while self._simulated_until + self.step_seconds <= elapsed:
            self._simulated_until += self.step_seconds
            with self._press_lock:
                presses, self._pending_presses = self._pending_presses, []
            for press_row, press_column in presses:
                self._apply_press(press_row, press_column)
            self._step(self._simulated_until)

    @abstractmethod
    def _reset(self) -> None:
        """Return the world to its starting state."""

    @abstractmethod
    def _step(self, now: float) -> None:
        """Advance the world by one `step_seconds` tick ending at `now`."""

    @abstractmethod
    def _apply_press(self, row: int, column: int) -> None:
        """Feed one key press into the world."""

    @abstractmethod
    def _render_key(self, row: int, column: int, elapsed: float) -> RGB:
        """Colour of one key given the current world state."""


class _Grain:
    """One grain of sand: its colour and how recently it moved."""

    __slots__ = ("color", "heat")

    def __init__(self, color: RGB):
        self.color = color
        #: 1.0 while falling, cooling toward 0.0 once settled. Moving grains
        #: glow brighter than resting ones so motion reads at a glance.
        self.heat = 1.0


class SandfallTheme(SimulationTheme):
    """
    Falling-sand physics. Every key press drops a grain from that key; grains
    fall, tumble off piles and settle on the bottom row. A full bottom row
    flashes white and clears, and everything above drops into its place.

    Grains also drift in on their own, so the board keeps moving when idle.
    """

    name = "sandfall"
    description = "Falling-sand physics: each key press drops a grain that piles up and clears"
    frames_per_second = 30

    # The sand is the effect, so keep it at full strength under --reactive and
    # keep the bubbles small: a splash where the grain was dropped, not a wave
    # that washes over the pile.
    reactive_base_brightness = 1.0
    reactive_bubble_lifetime = 0.5
    reactive_bubble_radius = 2.2

    _GRAIN_COLORS = [
        hex_to_rgb("#ffb627"),  # desert gold
        hex_to_rgb("#ff5d73"),  # coral
        hex_to_rgb("#2ec4b6"),  # lagoon teal
        hex_to_rgb("#9b5de5"),  # dusk violet
        hex_to_rgb("#f15bb5"),  # orchid
        hex_to_rgb("#00bbf9"),  # sky blue
    ]
    #: Empty air, top of the board to the bottom: a dim night sky, never black.
    _SKY_RAMP = [
        hex_to_rgb("#0b0a2a"),
        hex_to_rgb("#1a1040"),
        hex_to_rgb("#2a1438"),
    ]

    _AMBIENT_INTERVAL = 0.45        # seconds between self-dropped grains
    _COOL_PER_STEP = 0.06           # how fast a settled grain dims
    _RESTING_BRIGHTNESS = 0.55
    _FLASH_STEPS = 4                # length of the clearing flash
    _SKY_SHIMMER = 0.18
    _SEED = 87

    def _reset(self) -> None:
        self._random = random.Random(self._SEED)
        self._cells: List[List[Optional[_Grain]]] = [
            [None] * PIXEL_COLUMNS for _ in range(KEYBOARD_ROWS)
        ]
        self._next_color = 0
        self._next_ambient = 0.0
        self._flash_remaining = 0

    # ------------------------------------------------------------ input ---

    def _apply_press(self, row: int, column: int) -> None:
        pixels = _key_pixels(row, column)
        self._drop(row, pixels[len(pixels) // 2])

    def _drop(self, row: int, pixel: int) -> None:
        """
        Place a new grain at a cell, or the nearest free cell at or above it.

        Fast typing on one key can outrun gravity, so a blocked column spills
        into its neighbours rather than losing the press.
        """
        for spread in range(PIXEL_COLUMNS):
            for target_column in {pixel - spread, pixel + spread}:
                if not 0 <= target_column < PIXEL_COLUMNS:
                    continue
                for target_row in range(row, -1, -1):
                    if self._cells[target_row][target_column] is None:
                        self._place(target_row, target_column)
                        return
        # Every cell at or above this row is full: the pile has nowhere to go,
        # so clear the bottom row early.
        self._start_clear()

    def _place(self, row: int, column: int) -> None:
        color = self._GRAIN_COLORS[self._next_color % len(self._GRAIN_COLORS)]
        self._next_color += 1
        self._cells[row][column] = _Grain(color)

    # ---------------------------------------------------------- physics ---

    def _step(self, now: float) -> None:
        if self._flash_remaining:
            self._flash_remaining -= 1
            if self._flash_remaining == 0:
                self._collapse_bottom_row()
            return

        if now >= self._next_ambient:
            self._next_ambient = now + self._AMBIENT_INTERVAL
            self._drop(0, self._random.randrange(PIXEL_COLUMNS))

        self._fall()

        if all(cell is not None for cell in self._cells[-1]):
            self._start_clear()

    def _fall(self) -> None:
        """Move every grain one cell: straight down, else diagonally down."""
        # Bottom-up, so a grain that moves is not moved again in the same step.
        for row in range(KEYBOARD_ROWS - 2, -1, -1):
            columns = list(range(PIXEL_COLUMNS))
            # Random sweep order stops piles from always leaning one way.
            self._random.shuffle(columns)
            for column in columns:
                grain = self._cells[row][column]
                if grain is None:
                    continue
                target = self._landing_column(row, column)
                if target is None:
                    grain.heat = max(0.0, grain.heat - self._COOL_PER_STEP)
                    continue
                grain.heat = 1.0
                self._cells[row][column] = None
                self._cells[row + 1][target] = grain

        for grain in self._cells[-1]:
            if grain is not None:
                grain.heat = max(0.0, grain.heat - self._COOL_PER_STEP)

    def _landing_column(self, row: int, column: int) -> Optional[int]:
        below = self._cells[row + 1]
        if below[column] is None:
            return column
        sides = [column - 1, column + 1]
        self._random.shuffle(sides)
        for side in sides:
            if 0 <= side < PIXEL_COLUMNS and below[side] is None and self._cells[row][side] is None:
                return side
        return None

    def _start_clear(self) -> None:
        if not self._flash_remaining:
            self._flash_remaining = self._FLASH_STEPS

    def _collapse_bottom_row(self) -> None:
        self._cells.pop()
        self._cells.insert(0, [None] * PIXEL_COLUMNS)
        for row in self._cells:
            for grain in row:
                if grain is not None:
                    grain.heat = 1.0

    # -------------------------------------------------------- rendering ---

    def _render_key(self, row: int, column: int, elapsed: float) -> RGB:
        grains = [self._cells[row][pixel] for pixel in _key_pixels(row, column)]
        grains = [grain for grain in grains if grain is not None]

        if not grains:
            return self._sky(row, column, elapsed)

        # A wide key covering several cells shows its brightest grain.
        grain = max(grains, key=lambda item: item.heat)
        brightness = self._RESTING_BRIGHTNESS + (1.0 - self._RESTING_BRIGHTNESS) * grain.heat
        color = scale_brightness(grain.color, brightness)

        if self._flash_remaining and row == KEYBOARD_ROWS - 1:
            flash = self._flash_remaining / self._FLASH_STEPS
            color = _mix(color, _WHITE, flash)
        return color

    def _sky(self, row: int, column: int, elapsed: float) -> RGB:
        base = sample_ramp(self._SKY_RAMP, row / (KEYBOARD_ROWS - 1))
        # A slow shimmer so empty air is alive but never competes with sand.
        phase = physical_x(row, column) * 0.7 + row * 1.3 - elapsed * 1.1
        return scale_brightness(base, 1.0 + self._SKY_SHIMMER * math.sin(phase))
