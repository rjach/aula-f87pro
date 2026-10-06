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


class _Spark:
    """One spark thrown off a strike, in key-width units."""

    __slots__ = ("x", "y", "velocity_x", "velocity_y", "age", "lifetime")

    def __init__(self, x: float, y: float, velocity_x: float, velocity_y: float,
                 lifetime: float):
        self.x = x
        self.y = y
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y
        self.age = 0.0
        self.lifetime = lifetime


class ForgeTheme(SimulationTheme):
    """
    A blacksmith's forge where typing is the hammer.

    Left alone, the forge works itself: flames churn up from the bed, an
    unseen smith hammers a rhythm that wanders across the board throwing
    sparks, and every few seconds the bellows push a bright wave from the
    bottom row to the top. The moment you type, the smith steps aside and
    your own key presses are the hammer: that spot flashes white-hot, sparks
    fly up from it, and the heat spreads, rises and cools.

    Momentum is what makes this different from a ripple theme. Sustained
    typing stokes the forge bed along the bottom row, so a long run of steady
    work takes the whole board from red through orange to white-hot, and it
    settles back into the idle show a few seconds after you stop.
    """

    name = "forge"
    description = "Typing is the hammer: strikes throw sparks, steady flow heats the board white-hot"
    frames_per_second = 45
    step_seconds = 1 / 30

    # The forge already answers every keystroke, so keep it at full strength
    # under --reactive and shrink the bubbles to a brief flash at the anvil.
    reactive_base_brightness = 1.0
    reactive_bubble_lifetime = 0.3
    reactive_bubble_radius = 1.5

    #: Banked coal through to white-hot, coolest first. It stays in fire
    #: colours all the way down so the idle board and a strike feel like the
    #: same forge.
    _HEAT_RAMP = [
        hex_to_rgb("#6e1204"),  # banked coal, still clearly lit
        hex_to_rgb("#c41e08"),  # cherry red
        hex_to_rgb("#ff3c0a"),  # flame red
        hex_to_rgb("#ff7a00"),  # orange
        hex_to_rgb("#ffc400"),  # yellow heat
        hex_to_rgb("#fff4c2"),  # white-hot
    ]
    _SPARK_HOT = hex_to_rgb("#fff1b0")
    _SPARK_COOL = hex_to_rgb("#ff7a00")

    _STRIKE_HEAT = 0.95             # added to the struck key
    _STRIKE_SPREAD = 0.35           # added to its left and right neighbours
    _SPARKS_PER_STRIKE = 3

    #: Seconds for heat to fall to ~37%. Short enough that a strike reads as a
    #: flash, long enough that a typed word leaves a glowing trail behind it.
    _COOLING_TIME = 0.9
    _DIFFUSION = 0.12               # share of heat swapped with neighbours per step
    _CONVECTION = 0.10              # share of heat each cell hands to the row above

    _MOMENTUM_PER_PRESS = 0.06
    #: Seconds for momentum to fall to ~37% once typing stops. At ~5 keys/s
    #: (steady typing) momentum saturates; at ~2 keys/s it settles near half.
    _MOMENTUM_DECAY_TIME = 4.0
    _BED_IDLE_HEAT = 0.12           # the bed smoulders even with no typing
    _BED_FLOW_HEAT = 1.0            # extra bed heat at full momentum
    _BED_FLICKER = 0.08
    #: Heat the whole board soaks up at full momentum, at the top row and at
    #: the bed. Momentum curves through `_MOMENTUM_CURVE` first, so a few
    #: stray keys barely warm the steel and only real flow lights it up.
    _SOAK_TOP = 0.45
    _SOAK_BOTTOM = 0.8
    _MOMENTUM_CURVE = 1.6

    _SPARK_GRAVITY = 14.0           # rows per second squared, pulling down
    _SPARK_RADIUS = 0.5             # keys
    _MAX_SPARKS = 40

    # The idle smith: a hammer rhythm that walks the board on its own.
    _SMITH_INTERVAL = 0.22          # seconds between its strikes
    _SMITH_HEAT = 0.85
    _SMITH_SPARKS = 2
    #: Seconds after your last key press before the smith takes over again,
    #: so your own strikes are never confused with its.
    _SMITH_STANDBY = 2.5

    # Flames churning up from the bed, always on underneath everything.
    _FLAME_BASE = 0.42              # heat at the bed
    _FLAME_FALLOFF = 0.30           # heat lost toward the top row
    _FLAME_CHURN = 0.18
    _FLAME_RISE_SPEED = 3.2         # how fast flame fronts climb

    # The bellows: a bright wave pushed from the bed to the top row.
    _BELLOWS_PERIOD = 4.5           # seconds between breaths
    _BELLOWS_SPEED = 6.0            # rows per second
    _BELLOWS_WIDTH = 0.9            # rows
    _BELLOWS_HEAT = 0.55

    _MIN_BRIGHTNESS = 0.9
    _SEED = 87

    def _reset(self) -> None:
        self._random = random.Random(self._SEED)
        self._heat: List[List[float]] = [
            [0.0] * PIXEL_COLUMNS for _ in range(KEYBOARD_ROWS)
        ]
        self._sparks: List[_Spark] = []
        self._momentum = 0.0
        self._next_smith_beat = 0.0
        self._last_press = -self._SMITH_STANDBY
        self._smith_beat = 0
        self._now = 0.0

    @property
    def momentum(self) -> float:
        """How stoked the forge is, 0.0 (cold) to 1.0 (sustained flow)."""
        return self._momentum

    # ------------------------------------------------------------ input ---

    def _apply_press(self, row: int, column: int) -> None:
        self._momentum = min(1.0, self._momentum + self._MOMENTUM_PER_PRESS)
        self._last_press = self._now
        pixels = _key_pixels(row, column)
        self._strike(row, pixels, self._STRIKE_HEAT, self._SPARKS_PER_STRIKE)

    def _strike(self, row: int, pixels: Tuple[int, ...], heat: float, spark_count: int) -> None:
        cells = self._heat[row]
        for pixel in pixels:
            cells[pixel] += heat
        for side in (pixels[0] - 1, pixels[-1] + 1):
            if 0 <= side < PIXEL_COLUMNS:
                cells[side] += heat * self._STRIKE_SPREAD

        center = (pixels[0] + pixels[-1]) / 2 + 0.5
        for _ in range(spark_count):
            if len(self._sparks) >= self._MAX_SPARKS:
                self._sparks.pop(0)
            self._sparks.append(_Spark(
                x=center,
                y=float(row),
                velocity_x=self._random.uniform(-4.0, 4.0),
                velocity_y=-self._random.uniform(7.0, 12.0),
                lifetime=self._random.uniform(0.45, 0.8),
            ))

    # ---------------------------------------------------------- physics ---

    def _step(self, now: float) -> None:
        dt = self.step_seconds
        self._momentum *= math.exp(-dt / self._MOMENTUM_DECAY_TIME)

        self._now = now
        smith_is_free = now - self._last_press >= self._SMITH_STANDBY
        if now >= self._next_smith_beat:
            self._next_smith_beat = now + self._SMITH_INTERVAL
            if smith_is_free:
                self._smith_strike()

        self._stoke_bed(now)
        self._spread_heat(dt)
        self._move_sparks(dt)

    def _smith_strike(self) -> None:
        """
        One beat of the idle hammer rhythm: tap, tap, tap, BANG.

        The strike point traces two sine paths at unrelated rates, so it
        sweeps the whole board smoothly without ever repeating a loop.
        """
        beat = self._smith_beat
        self._smith_beat += 1
        pixel = round((PIXEL_COLUMNS - 1) * (0.5 + 0.5 * math.sin(beat * 0.31)))
        row = round((KEYBOARD_ROWS - 1) * (0.5 + 0.5 * math.sin(beat * 0.17 + 1.0)))
        is_accent = beat % 4 == 3
        heat = self._SMITH_HEAT * (1.4 if is_accent else 0.8)
        sparks = self._SMITH_SPARKS * (3 if is_accent else 1)
        self._strike(row, (pixel,), heat, spark_count=sparks)

    def _stoke_bed(self, now: float) -> None:
        """Hold the bottom row at a heat set by momentum, flickering per cell."""
        target = self._BED_IDLE_HEAT + self._BED_FLOW_HEAT * self._momentum
        bed = self._heat[-1]
        for pixel in range(PIXEL_COLUMNS):
            flicker = self._BED_FLICKER * math.sin(now * 9.0 + pixel * 2.3)
            bed[pixel] = max(bed[pixel], target + flicker)

    def _spread_heat(self, dt: float) -> None:
        cooling = math.exp(-dt / self._COOLING_TIME)
        old = self._heat
        new = [[0.0] * PIXEL_COLUMNS for _ in range(KEYBOARD_ROWS)]
        for row in range(KEYBOARD_ROWS):
            for pixel in range(PIXEL_COLUMNS):
                here = old[row][pixel]
                left = old[row][pixel - 1] if pixel > 0 else here
                right = old[row][pixel + 1] if pixel < PIXEL_COLUMNS - 1 else here
                new[row][pixel] += here + self._DIFFUSION * ((left + right) / 2 - here)
                # Hot air rises: hand a share of this cell's heat to the one
                # above. Moved, not copied, or the board heats itself; off the
                # top row it vents away, or the function row would pool heat.
                rising = self._CONVECTION * here
                new[row][pixel] -= rising
                if row > 0:
                    new[row - 1][pixel] += rising
        self._heat = [[min(1.5, cell * cooling) for cell in cells] for cells in new]

    def _move_sparks(self, dt: float) -> None:
        alive = []
        for spark in self._sparks:
            spark.age += dt
            spark.velocity_y += self._SPARK_GRAVITY * dt
            spark.x += spark.velocity_x * dt
            spark.y += spark.velocity_y * dt
            if spark.age < spark.lifetime and -1.0 < spark.y < KEYBOARD_ROWS:
                alive.append(spark)
        self._sparks = alive

    # -------------------------------------------------------- rendering ---

    def _render_key(self, row: int, column: int, elapsed: float) -> RGB:
        heat = max(self._heat[row][pixel] for pixel in _key_pixels(row, column))
        key_x = physical_x(row, column)
        heat = min(1.0, max(heat, self._soak(row), self._flames(key_x, row, elapsed)))
        color = sample_ramp(self._HEAT_RAMP, heat)
        color = scale_brightness(color, self._MIN_BRIGHTNESS + (1.0 - self._MIN_BRIGHTNESS) * heat)

        return self._add_sparks(color, key_x, row)

    def _soak(self, row: int) -> float:
        """Background heat from momentum, hotter toward the bed."""
        depth = row / (KEYBOARD_ROWS - 1)
        reach = self._SOAK_TOP + (self._SOAK_BOTTOM - self._SOAK_TOP) * depth
        return reach * self._momentum ** self._MOMENTUM_CURVE

    def _flames(self, key_x: float, row: int, elapsed: float) -> float:
        """
        Always-on fire under everything else: churning flame fronts climbing
        from the bed, plus the bellows wave.
        """
        height = (KEYBOARD_ROWS - 1 - row) / (KEYBOARD_ROWS - 1)
        churn = (
            math.sin(key_x * 0.9 - elapsed * self._FLAME_RISE_SPEED + row * 1.3)
            + math.sin(key_x * 0.41 + elapsed * 1.7)
        ) * 0.5
        flame = self._FLAME_BASE - self._FLAME_FALLOFF * height + self._FLAME_CHURN * churn

        front = (elapsed % self._BELLOWS_PERIOD) * self._BELLOWS_SPEED
        distance = (KEYBOARD_ROWS - 1 - row) - front
        bellows = math.exp(-(distance * distance) / (2 * self._BELLOWS_WIDTH ** 2))
        return flame + self._BELLOWS_HEAT * bellows

    def _add_sparks(self, color: RGB, key_x: float, row: int) -> RGB:
        red, green, blue = color
        for spark in self._sparks:
            distance_sq = (key_x - spark.x) ** 2 + (row - spark.y) ** 2
            glow = math.exp(-distance_sq / (2 * self._SPARK_RADIUS ** 2))
            if glow < 0.02:
                continue
            fade = 1.0 - spark.age / spark.lifetime
            tint = _mix(self._SPARK_COOL, self._SPARK_HOT, fade)
            strength = glow * fade
            red += tint[0] * strength
            green += tint[1] * strength
            blue += tint[2] * strength
        return (min(255, int(red)), min(255, int(green)), min(255, int(blue)))
