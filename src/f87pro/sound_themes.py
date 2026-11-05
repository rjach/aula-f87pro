"""
More sound-reactive themes, built on `sound.AudioTheme`.

Each one reads the same tracked spectrum as `pulse` but draws it as a
different picture: fire, a scrolling spectrogram, rain, and a reactor core.
All of them drive one scene from inputs blended by `presence`, so the idle
show and the music are the same world and the hand-over has no seam.
"""
import math
import random
from typing import List

from .layout import BOARD_WIDTH_UNITS, PIXEL_COLUMNS, physical_x
from .simulation import FIRE_RAMP, _mix, _Spark, add_spark_light, move_sparks
from .sound import (
    BASS_BANDS,
    MID_BANDS,
    TREBLE_BANDS,
    AudioTheme,
    _add_light,
    _hue_color,
    _ring_light,
    _Wave,
)
from .theme_base import (
    KEYBOARD_ROWS,
    RGB,
    _stable_jitter,
    hex_to_rgb,
    sample_ramp,
    scale_brightness,
)

_WHITE: RGB = (255, 255, 255)
_BOTTOM_ROW = KEYBOARD_ROWS - 1


def _height(row: int) -> float:
    """0.0 on the bottom row, 1.0 on the function row."""
    return (_BOTTOM_ROW - row) / _BOTTOM_ROW


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# --------------------------------------------------------------------------
# blaze
# --------------------------------------------------------------------------

class BlazeTheme(AudioTheme):
    """
    A fire that burns to the music.

    Bass sets how high the flames climb, with each column also following the
    band under it (bass in the middle, treble at the edges), so the fire has
    the shape of the song. Every beat throws a burst of sparks up from the
    bottom row and kicks the flames higher for a moment, and treble crackles
    along the flame tips.

    In silence it smoulders: low flames in the same reds and oranges, with
    the odd spark, never a cold colour. Under --reactive each key press
    flares the key you hit and throws a couple of sparks.
    """

    name = "blaze"
    description = "Fire that burns to your Mac's sound: bass lifts the flames, beats throw sparks"

    #: How high the flames reach (0-1 of the board) while idle, and sway.
    _IDLE_REACH = 0.45
    _IDLE_SWAY = 0.10
    #: Flame reach with music: never below the floor, up to floor + range.
    _MUSIC_REACH_FLOOR = 0.15
    _MUSIC_REACH_RANGE = 0.8
    #: Share of a column's reach set by the overall bass; the rest follows
    #: the band under that column.
    _BASS_SHARE = 0.55
    #: A beat lifts every flame by this much, decaying over `_KICK_DECAY_TIME`.
    _KICK_REACH = 0.15
    _KICK_DECAY_TIME = 0.14

    #: Heat lost per unit of height: a flame reaching the top row has its
    #: tip at ~0.1 heat, so only the bed goes white-hot.
    _HEAT_FALLOFF = 0.9
    #: Drifting glow above the flames, so the upper rows smoulder rather
    #: than sit at one flat coal colour.
    _EMBER_GLOW = 0.07
    _EMBER_DRIFT = 1.3
    _CHURN = 0.14
    _RISE_SPEED = 3.0
    #: Treble flicker at the flame tips, and the small flicker idle keeps.
    _CRACKLE = 0.45
    _IDLE_CRACKLE = 0.12
    _CRACKLE_SPEED = 23.0
    _TIP_WIDTH = 0.3

    _BEAT_SPARKS = 6
    _IDLE_SPARK_INTERVAL = 0.8
    _IDLE_SPARKS = 2
    _PRESS_SPARKS = 2
    _SPARK_GRAVITY = 12.0
    _SPARK_RADIUS = 0.55
    _MAX_SPARKS = 48

    _FLARE_HEAT = 0.8
    _FLARE_LIFETIME = 0.5
    _FLARE_RADIUS = 1.1
    _MAX_FLARES = 16

    _MIN_BRIGHTNESS = 0.9
    _SEED = 451

    def _reset_scene(self) -> None:
        self._random = random.Random(self._SEED)
        self._sparks: List[_Spark] = []
        self._flares: List[_Wave] = []
        self._kick = 0.0
        self._next_idle_spark = 0.0

    def _apply_press(self, row: int, column: int) -> None:
        key_x = physical_x(row, column)
        if len(self._flares) >= self._MAX_FLARES:
            self._flares.pop(0)
        self._flares.append(_Wave(key_x, row, 1.0, 0.0))
        self._throw_sparks(key_x, row, self._PRESS_SPARKS)

    def _step_scene(self, now: float, dt: float) -> None:
        if self._tracker.take_beat():
            self._kick = 1.0
            for _ in range(self._BEAT_SPARKS):
                self._throw_sparks(self._random.uniform(1.0, BOARD_WIDTH_UNITS - 1.0),
                                   _BOTTOM_ROW, 1)
        # Idle sparks thin out as the music takes over and beats supply them.
        if now >= self._next_idle_spark:
            self._next_idle_spark = now + self._IDLE_SPARK_INTERVAL
            if self._random.random() > self.presence:
                self._throw_sparks(self._random.uniform(2.0, BOARD_WIDTH_UNITS - 2.0),
                                   _BOTTOM_ROW, self._IDLE_SPARKS)

        self._kick *= math.exp(-dt / self._KICK_DECAY_TIME)
        self._sparks = move_sparks(self._sparks, dt, self._SPARK_GRAVITY)
        for flare in self._flares:
            flare.age += dt
        self._flares = [flare for flare in self._flares if flare.age < self._FLARE_LIFETIME]

    def _throw_sparks(self, x: float, row: float, count: int) -> None:
        for _ in range(count):
            if len(self._sparks) >= self._MAX_SPARKS:
                self._sparks.pop(0)
            self._sparks.append(_Spark(
                x=x,
                y=float(row),
                velocity_x=self._random.uniform(-3.0, 3.0),
                velocity_y=-self._random.uniform(8.0, 13.0),
                lifetime=self._random.uniform(0.5, 0.9),
            ))

    def _render_key(self, row: int, column: int, elapsed: float) -> RGB:
        key_x = physical_x(row, column)
        height = _height(row)
        reach = self._reach(key_x, elapsed)

        churn = (
            math.sin(key_x * 0.9 - elapsed * self._RISE_SPEED + row * 1.3)
            + math.sin(key_x * 0.41 + elapsed * 1.7)
        ) * 0.5
        heat = reach - height * self._HEAT_FALLOFF + self._CHURN * churn
        embers = self._EMBER_GLOW * (1.0 + math.sin(key_x * 0.7 + row * 2.1 + elapsed * self._EMBER_DRIFT))
        heat = max(heat, embers)

        crackle_strength = self._with_music(self._IDLE_CRACKLE,
                                            self._CRACKLE * self._band_mean(TREBLE_BANDS))
        near_tip = max(0.0, 1.0 - abs(height - reach) / self._TIP_WIDTH)
        flicker = math.sin(elapsed * self._CRACKLE_SPEED + _stable_jitter(row, column) * 40.0)
        heat += crackle_strength * near_tip * flicker

        for flare in self._flares:
            distance = math.hypot(key_x - flare.x, row - flare.row)
            fade = 1.0 - flare.age / self._FLARE_LIFETIME
            heat += self._FLARE_HEAT * fade * math.exp(-(distance / self._FLARE_RADIUS) ** 2)

        heat = _clamp(heat)
        color = sample_ramp(FIRE_RAMP, heat)
        color = scale_brightness(color, self._MIN_BRIGHTNESS + (1.0 - self._MIN_BRIGHTNESS) * heat)
        return add_spark_light(color, self._sparks, key_x, row, self._SPARK_RADIUS)

    def _reach(self, key_x: float, elapsed: float) -> float:
        """How high the flame above this column climbs, 0-1 of the board."""
        idle = self._IDLE_REACH + self._IDLE_SWAY * math.sin(elapsed * 0.7 + key_x * 0.35)
        spread = min(1.0, abs(key_x / BOARD_WIDTH_UNITS - 0.5) * 2)
        drive = (self._BASS_SHARE * self._band_mean(BASS_BANDS)
                 + (1.0 - self._BASS_SHARE) * self._band_at(spread))
        music = self._MUSIC_REACH_FLOOR + self._MUSIC_REACH_RANGE * drive
        return self._with_music(idle, music) + self._KICK_REACH * self._kick


# --------------------------------------------------------------------------
# waterfall
# --------------------------------------------------------------------------

class WaterfallTheme(AudioTheme):
    """
    A scrolling spectrogram: the last moments of the song, left to right.

    Each row is a slice of the spectrum, bass on the bottom row and treble on
    the function row. The right edge is the sound right now, and every column
    slides left as time passes, so a melody climbing the scale reads as a
    diagonal and a drop reads as a wall of light sweeping across the board.
    Beats are stamped into the column that heard them and travel with it.

    In silence it scrolls a slow made-up song of its own, with a soft beat.
    """

    name = "waterfall"
    description = "Scrolling spectrogram of your Mac's sound: bass at the bottom, now on the right"

    #: Seconds between columns. 18 columns of this is ~1.6 s of history.
    _SCROLL_INTERVAL = 0.09
    _BANDS_PER_ROW = 2

    #: Deep violet through magenta to hot pink, quietest first.
    _RAMP = [
        hex_to_rgb("#3a0a6e"),
        hex_to_rgb("#7a17c9"),
        hex_to_rgb("#d21fbf"),
        hex_to_rgb("#ff3d8b"),
        hex_to_rgb("#ffb3d9"),
    ]
    _MIN_BRIGHTNESS = 0.45
    _BEAT_WHITENING = 0.55

    _IDLE_BEAT_PERIOD = 1.8
    _IDLE_BEAT_STRENGTH = 0.5

    def _reset_scene(self) -> None:
        self._history: List[List[float]] = [[0.0] * KEYBOARD_ROWS for _ in range(PIXEL_COLUMNS)]
        self._history_beats: List[float] = [0.0] * PIXEL_COLUMNS
        self._live: List[float] = [0.0] * KEYBOARD_ROWS
        self._live_beat = 0.0
        self._since_push = 0.0
        self._next_idle_beat = self._IDLE_BEAT_PERIOD

    def _apply_press(self, row: int, column: int) -> None:
        # A key press lights the column under that key, which then scrolls
        # left from where you hit it like any other sound.
        index = self._column_under(physical_x(row, column))
        if index >= PIXEL_COLUMNS:
            self._live[row] = 1.0
        else:
            self._history[index][row] = 1.0

    def _step_scene(self, now: float, dt: float) -> None:
        heard = [self._with_music(self._idle_level(row, now), self._row_level(row))
                 for row in range(KEYBOARD_ROWS)]
        # Keep the loudest moment since the last push, so short transients
        # still make it into the history rather than falling between columns.
        self._live = [max(live, level) for live, level in zip(self._live, heard)]

        if self._tracker.take_beat():
            self._live_beat = 1.0
        if now >= self._next_idle_beat:
            self._next_idle_beat = now + self._IDLE_BEAT_PERIOD
            self._live_beat = max(self._live_beat, self._IDLE_BEAT_STRENGTH * (1.0 - self.presence))

        self._since_push += dt
        if self._since_push >= self._SCROLL_INTERVAL:
            self._since_push -= self._SCROLL_INTERVAL
            self._history = self._history[1:] + [self._live]
            self._history_beats = self._history_beats[1:] + [self._live_beat]
            self._live = heard
            self._live_beat = 0.0

    def _row_level(self, row: int) -> float:
        first = (_BOTTOM_ROW - row) * self._BANDS_PER_ROW
        return self._band_mean(range(first, first + self._BANDS_PER_ROW))

    @staticmethod
    def _idle_level(row: int, now: float) -> float:
        return _clamp(0.42 + 0.28 * math.sin(now * 1.1 + row * 0.9)
                      + 0.18 * math.sin(now * 2.7 - row * 1.9 + 1.0))

    def _render_key(self, row: int, column: int, elapsed: float) -> RGB:
        # Column i is centred at i + 0.5 - phase, so content glides left
        # between pushes. Index PIXEL_COLUMNS is the live, still-filling one.
        position = self._position_under(physical_x(row, column))
        lower = int(position)
        upper = min(lower + 1, PIXEL_COLUMNS)
        blend = position - lower

        level = self._column_level(lower, row) * (1 - blend) + self._column_level(upper, row) * blend
        beat = self._column_beat(lower) * (1 - blend) + self._column_beat(upper) * blend

        color = scale_brightness(sample_ramp(self._RAMP, level),
                                 self._MIN_BRIGHTNESS + (1.0 - self._MIN_BRIGHTNESS) * level)
        return _mix(color, _WHITE, beat * self._BEAT_WHITENING * (0.4 + 0.6 * level))

    def _position_under(self, key_x: float) -> float:
        """Fractional history index shown at `key_x`; PIXEL_COLUMNS is live."""
        phase = self._since_push / self._SCROLL_INTERVAL
        return max(0.0, min(float(PIXEL_COLUMNS), key_x - 0.5 + phase))

    def _column_under(self, key_x: float) -> int:
        return round(self._position_under(key_x))

    def _column_level(self, index: int, row: int) -> float:
        return self._live[row] if index >= PIXEL_COLUMNS else self._history[index][row]

    def _column_beat(self, index: int) -> float:
        return self._live_beat if index >= PIXEL_COLUMNS else self._history_beats[index]


# --------------------------------------------------------------------------
# monsoon
# --------------------------------------------------------------------------

class _Drop:
    """A raindrop landing on a key and rippling outward."""

    __slots__ = ("x", "row", "age", "strength", "speed", "lifetime", "width")

    def __init__(self, x: float, row: float, strength: float, speed: float,
                 lifetime: float, width: float):
        self.x = x
        self.row = row
        self.age = 0.0
        self.strength = strength
        self.speed = speed
        self.lifetime = lifetime
        self.width = width


class MonsoonTheme(AudioTheme):
    """
    The music as rain on dark water.

    Treble sets how hard it rains: hi-hats and cymbals land as small drops on
    random keys, each rippling outward. Every beat drops one big drop whose
    rings spread across the board and run through the small ones. Bass
    swells a glow up from the bottom rows, like the sea lifting.

    In silence it drizzles over a slow swell, in the same blues.
    """

    name = "monsoon"
    description = "Rain on dark water: treble falls as drops, beats send big ripples, bass swells"

    _WATER = [
        hex_to_rgb("#041b3d"),  # deep water, still clearly lit
        hex_to_rgb("#073f80"),
        hex_to_rgb("#0b74bd"),
        hex_to_rgb("#1cc4e8"),
    ]
    _DROP_TINT = hex_to_rgb("#c4f4ff")

    _BASE_GLOW = 0.12
    #: Swell height at full bass, falling off upward over `_SWELL_DEPTH` rows.
    _SWELL = 0.75
    _SWELL_DEPTH = 1.7
    _IDLE_SWELL = 0.28
    _IDLE_SWELL_SWAY = 0.14
    _MIN_BRIGHTNESS = 0.6

    #: Drops per second: idle drizzle, and with music a floor plus treble.
    _IDLE_RAIN = 3.0
    _MUSIC_RAIN_FLOOR = 2.0
    _MUSIC_RAIN_RANGE = 22.0

    _SMALL_DROP = dict(strength=0.6, speed=5.0, lifetime=0.55, width=0.55)
    _BIG_DROP = dict(strength=1.0, speed=9.0, lifetime=1.0, width=0.9)
    _PRESS_DROP = dict(strength=0.8, speed=6.0, lifetime=0.7, width=0.6)
    #: The splash at the centre of a fresh drop fades this fast.
    _SPLASH_FADE_RATE = 6.0
    _MAX_DROPS = 28
    _SEED = 1984

    def _reset_scene(self) -> None:
        self._random = random.Random(self._SEED)
        self._drops: List[_Drop] = []
        self._rain_owed = 0.0

    def _apply_press(self, row: int, column: int) -> None:
        self._add_drop(physical_x(row, column), row, self._PRESS_DROP)

    def _step_scene(self, now: float, dt: float) -> None:
        if self._tracker.take_beat():
            self._add_drop(self._random.uniform(3.0, BOARD_WIDTH_UNITS - 3.0),
                           self._random.uniform(1.0, _BOTTOM_ROW - 1.0), self._BIG_DROP)

        music_rain = self._MUSIC_RAIN_FLOOR + self._MUSIC_RAIN_RANGE * self._band_mean(TREBLE_BANDS)
        self._rain_owed += self._with_music(self._IDLE_RAIN, music_rain) * dt
        while self._rain_owed >= 1.0:
            self._rain_owed -= 1.0
            self._add_drop(self._random.uniform(0.0, BOARD_WIDTH_UNITS),
                           self._random.randint(0, _BOTTOM_ROW), self._SMALL_DROP)

        for drop in self._drops:
            drop.age += dt
        self._drops = [drop for drop in self._drops if drop.age < drop.lifetime]

    def _add_drop(self, x: float, row: float, kind: dict) -> None:
        if len(self._drops) >= self._MAX_DROPS:
            self._drops.pop(0)
        self._drops.append(_Drop(x, row, **kind))

    def _render_key(self, row: int, column: int, elapsed: float) -> RGB:
        key_x = physical_x(row, column)
        idle_swell = self._IDLE_SWELL + self._IDLE_SWELL_SWAY * math.sin(elapsed * 0.6 + key_x * 0.3)
        swell = self._with_music(idle_swell, self._SWELL * self._band_mean(BASS_BANDS))
        glow = self._BASE_GLOW + swell * math.exp(-(_BOTTOM_ROW - row) / self._SWELL_DEPTH)

        glow = _clamp(glow)
        color = scale_brightness(sample_ramp(self._WATER, glow),
                                 self._MIN_BRIGHTNESS + (1.0 - self._MIN_BRIGHTNESS) * glow)

        for drop in self._drops:
            fade = (1.0 - drop.age / drop.lifetime) ** 1.5
            ring = _ring_light(key_x, row, drop.x, drop.row, drop.age * drop.speed, drop.width)
            distance_sq = (key_x - drop.x) ** 2 + (row - drop.row) ** 2
            splash = math.exp(-distance_sq / 0.5) * max(0.0, 1.0 - drop.age * self._SPLASH_FADE_RATE)
            amount = (ring * fade + splash) * drop.strength
            if amount > 0.02:
                color = _add_light(color, self._DROP_TINT, amount)
        return color


# --------------------------------------------------------------------------
# core
# --------------------------------------------------------------------------

class CoreTheme(AudioTheme):
    """
    A reactor core in the middle of the board, in every colour at once.

    The music is drawn in circles rather than bars. Bass sets the size of the
    white-hot core, the mids light a ring around it, and treble flickers at
    the rim of the board. Each of those layers has its own hue, and the whole
    board sits on a colour wheel laid around the centre, so every direction
    out from the core is a different colour.

    The wheel is what moves with the song: it spins steadily, every beat
    turns it a step and fires a shockwave in a fresh colour, and a loud
    stretch heats the reactor, which spins the wheel faster, brightens the
    board and burns the core whiter. Quiet music lets it cool and slow.

    In silence the core breathes slowly and the wheel drifts, with a
    shockwave every few seconds.
    """

    name = "core"
    description = "Reactor core in a spinning colour wheel: bass sizes the core, beats fire shockwaves"

    _CENTER_X = BOARD_WIDTH_UNITS / 2
    _CENTER_ROW = _BOTTOM_ROW / 2
    #: Rows count this much more than key widths, so the core is a wide oval
    #: that fills the board's shape instead of a circle lost in the middle.
    _ROW_STRETCH = 1.6
    _MAX_RADIUS = math.hypot(BOARD_WIDTH_UNITS / 2, (_BOTTOM_ROW / 2) * _ROW_STRETCH)

    # Colour. Hues are fractions of the colour wheel.
    #: Hue turns once round the core: a full rainbow in every frame. The
    #: wheel wraps, so the seam behind the centre is invisible.
    _HUE_AROUND = 1.0
    #: Extra hue from the core out to the rim, bending the wheel into a swirl.
    _HUE_OUTWARD = 0.3
    #: Offsets of each layer from the wheel under it, so the core, the ring
    #: and the rim never share a colour.
    _RING_HUE_OFFSET = 0.33
    _RIM_HUE_OFFSET = 0.62
    _SHOCK_HUE_OFFSET = 0.5
    _BEAT_HUE_STEP = 0.09
    #: Wheel turns per second, idle and with the reactor fully hot.
    _IDLE_SPIN = 0.04
    _HOT_SPIN = 0.22

    #: Brightness of the wheel behind everything, cool and hot. Kept well
    #: lit so every key shows its colour, not just the lit shapes.
    _BACKDROP_COOL = 0.4
    _BACKDROP_HOT = 0.55
    _BACKDROP_SATURATION = 0.9
    #: How white the centre of the core burns, cool and hot.
    _CORE_WHITEN_COOL = 0.35
    _CORE_WHITEN_HOT = 0.85

    # Shape, all in 0-1 of the distance from the centre to the corner.
    _CORE_MIN = 0.08
    _CORE_RANGE = 0.25
    _CORE_EDGE = 0.1
    _RING_RADIUS = 0.55
    _RING_WIDTH = 0.1
    _RING_STRENGTH = 0.85
    _RIM_START = 0.7
    _RIM_STRENGTH = 0.8
    _RIM_FLICKER_SPEED = 19.0

    _KICK_CORE = 0.08
    _KICK_DECAY_TIME = 0.15
    _SHOCK_SPEED = 2.4              # radii per second
    _SHOCK_WIDTH = 0.07
    _SHOCK_LIFETIME = 0.55
    _SHOCK_STRENGTH = 0.85
    _SHOCK_SATURATION = 0.6
    _MAX_SHOCKS = 8

    #: Seconds for the reactor's temperature to follow loudness.
    _HEAT_TIME = 3.0
    _IDLE_TEMPERATURE = 0.15
    _IDLE_SHOCK_PERIOD = 3.2

    _PRESS_FLASH_LIFETIME = 0.35
    _PRESS_SATURATION = 0.35
    _MAX_PRESS_FLASHES = 12

    def _reset_scene(self) -> None:
        #: Shockwaves as waves from the centre; `hue_shift` holds the hue
        #: each was fired in, so it keeps its colour as the wheel turns.
        self._shocks: List[_Wave] = []
        self._presses: List[_Wave] = []
        self._kick = 0.0
        self._temperature = self._IDLE_TEMPERATURE
        self._hue = 0.0
        self._next_idle_shock = self._IDLE_SHOCK_PERIOD

    def _apply_press(self, row: int, column: int) -> None:
        if len(self._presses) >= self._MAX_PRESS_FLASHES:
            self._presses.pop(0)
        self._presses.append(_Wave(physical_x(row, column), row, 1.0, self._hue))

    def _step_scene(self, now: float, dt: float) -> None:
        if self._tracker.take_beat():
            self._hue += self._BEAT_HUE_STEP
            self._fire_shock()
        if now >= self._next_idle_shock:
            self._next_idle_shock = now + self._IDLE_SHOCK_PERIOD
            if self.presence < 0.5:
                self._fire_shock()

        target = self._with_music(self._IDLE_TEMPERATURE, self._tracker.loudness)
        self._temperature += (target - self._temperature) * (1.0 - math.exp(-dt / self._HEAT_TIME))
        self._hue += (self._IDLE_SPIN + self._HOT_SPIN * self._temperature) * dt
        self._kick *= math.exp(-dt / self._KICK_DECAY_TIME)

        for wave in self._shocks + self._presses:
            wave.age += dt
        self._shocks = [shock for shock in self._shocks if shock.age < self._SHOCK_LIFETIME]
        self._presses = [press for press in self._presses if press.age < self._PRESS_FLASH_LIFETIME]

    def _fire_shock(self) -> None:
        self._kick = 1.0
        if len(self._shocks) >= self._MAX_SHOCKS:
            self._shocks.pop(0)
        self._shocks.append(_Wave(self._CENTER_X, self._CENTER_ROW, self._SHOCK_STRENGTH,
                                  self._hue + self._SHOCK_HUE_OFFSET))

    def _render_key(self, row: int, column: int, elapsed: float) -> RGB:
        key_x = physical_x(row, column)
        across = key_x - self._CENTER_X
        down = (row - self._CENTER_ROW) * self._ROW_STRETCH
        radius = math.hypot(across, down) / self._MAX_RADIUS
        angle = math.atan2(down, across) / (2 * math.pi)
        wheel = self._hue + angle * self._HUE_AROUND + radius * self._HUE_OUTWARD
        heat = self._temperature

        backdrop = self._BACKDROP_COOL + (self._BACKDROP_HOT - self._BACKDROP_COOL) * heat
        color = scale_brightness(_hue_color(wheel, self._BACKDROP_SATURATION), backdrop)

        core, ring, rim = self._layers(row, column, radius, elapsed)
        color = _add_light(color, self._core_color(wheel, radius), core)
        color = _add_light(color, _hue_color(wheel + self._RING_HUE_OFFSET), ring)
        color = _add_light(color, _hue_color(wheel + self._RIM_HUE_OFFSET), rim)

        for shock in self._shocks:
            offset = (radius - shock.age * self._SHOCK_SPEED) / self._SHOCK_WIDTH
            amount = shock.strength * math.exp(-offset * offset) * (1.0 - shock.age / self._SHOCK_LIFETIME)
            if amount > 0.02:
                color = _add_light(color, _hue_color(shock.hue_shift + angle, self._SHOCK_SATURATION), amount)
        for press in self._presses:
            distance = math.hypot(key_x - press.x, row - press.row)
            amount = math.exp(-distance * distance) * (1.0 - press.age / self._PRESS_FLASH_LIFETIME)
            if amount > 0.02:
                color = _add_light(color, _hue_color(wheel + 0.5, self._PRESS_SATURATION), amount)
        return color

    def _layers(self, row: int, column: int, radius: float, elapsed: float):
        """How lit the core, the mid ring and the rim are at `radius`, 0-1 each."""
        bass = self._with_music(0.35 + 0.25 * math.sin(elapsed * 1.5), self._band_mean(BASS_BANDS))
        mids = self._with_music(0.4 + 0.2 * math.sin(elapsed * 0.8 + 1.0), self._band_mean(MID_BANDS))
        treble = self._with_music(0.15, self._band_mean(TREBLE_BANDS))

        core_size = self._CORE_MIN + self._CORE_RANGE * bass + self._KICK_CORE * self._kick
        outside = max(0.0, radius - core_size) / self._CORE_EDGE
        core = math.exp(-outside * outside)
        ring = mids * self._RING_STRENGTH * math.exp(-((radius - self._RING_RADIUS) / self._RING_WIDTH) ** 2)
        flicker = 0.5 + 0.5 * math.sin(elapsed * self._RIM_FLICKER_SPEED
                                       + _stable_jitter(row, column) * 40.0)
        rim = treble * self._RIM_STRENGTH * flicker * _clamp((radius - self._RIM_START) / (1 - self._RIM_START))
        return core, ring, rim

    def _core_color(self, wheel: float, radius: float) -> RGB:
        """The core takes the wheel's colour, burning whiter toward the centre."""
        whiten = self._CORE_WHITEN_COOL + (self._CORE_WHITEN_HOT - self._CORE_WHITEN_COOL) * self._temperature
        centre = math.exp(-(radius / max(self._CORE_MIN, 0.05)) ** 2)
        return _mix(_hue_color(wheel), _WHITE, whiten * (0.4 + 0.6 * centre))
