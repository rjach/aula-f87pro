"""
Sound-reactive themes.

These listen to whatever the Mac is playing (see `audio.py`) and treat the
levels as input into a small stepped world, the same way `simulation.py`
themes treat key presses.
"""
import colorsys
import math
import threading
from typing import List

from .audio import BAND_COUNT, AudioLevels, SpectrumTracker
from .layout import BOARD_WIDTH_UNITS, physical_x
from .simulation import SimulationTheme, _mix
from .theme_base import KEYBOARD_ROWS, RGB, scale_brightness

_WHITE: RGB = (255, 255, 255)
_MAX_CHANNEL = 255


def _hue_color(hue: float, saturation: float = 1.0) -> RGB:
    """A full-brightness colour at `hue` (any real number, used cyclically)."""
    red, green, blue = colorsys.hsv_to_rgb(hue % 1.0, saturation, 1.0)
    return (int(red * _MAX_CHANNEL), int(green * _MAX_CHANNEL), int(blue * _MAX_CHANNEL))


def _add_light(color: RGB, tint: RGB, amount: float) -> RGB:
    """Add `tint` on top of `color` like a light, clamped per channel."""
    return (
        min(_MAX_CHANNEL, int(color[0] + tint[0] * amount)),
        min(_MAX_CHANNEL, int(color[1] + tint[1] * amount)),
        min(_MAX_CHANNEL, int(color[2] + tint[2] * amount)),
    )


def _bar_fill(height: float, bar: float) -> float:
    """
    How lit a key at `height` is under a bar reaching `bar` (both 0-1, from
    the bottom row up). Soft-edged so a bar settles between rows smoothly.
    """
    return max(0.0, min(1.0, (bar * 1.1 - height) / 0.2 + 0.5))


class _Wave:
    """A ring of light spreading from a point: a beat, or a key press."""

    __slots__ = ("x", "row", "age", "strength", "hue_shift")

    def __init__(self, x: float, row: float, strength: float, hue_shift: float):
        self.x = x
        self.row = row
        self.age = 0.0
        self.strength = strength
        self.hue_shift = hue_shift


class PulseTheme(SimulationTheme):
    """
    A spectrum equalizer driven by the system's sound.

    Bass sits in the middle of the board and treble at the edges, so the bars
    are mirrored like a speaker cone. Every bass beat sends a ring out from
    the spacebar, kicks the whole board brighter, and steps the colours round
    the wheel, so the board changes with the track rather than on a timer.

    When nothing is playing, or the audio cannot be captured, it plays its
    own show: a slow rainbow equalizer breathing as if music were on, with a
    heartbeat ring every few seconds. Sound fades the show out and fades the
    real spectrum in; silence for a moment brings the show back.
    """

    name = "pulse"
    description = "Equalizer that dances to your Mac's sound; plays its own show in silence"
    frames_per_second = 60
    step_seconds = 1 / 60
    listens_to_audio = True

    # Full strength under --reactive, with only a short flash per key so the
    # music stays the star.
    reactive_base_brightness = 1.0
    reactive_bubble_lifetime = 0.35
    reactive_bubble_radius = 2.0

    #: Seconds of audio in one line from the helper (its `windowSeconds`).
    _AUDIO_WINDOW = 1 / 60
    #: With no audio for this long, assume the stream stalled and let the
    #: tracker fall back toward the idle show.
    _AUDIO_STALL_SECONDS = 0.25
    #: Bound on queued audio windows if the frame loop falls behind.
    _MAX_PENDING_AUDIO = 30

    # -- music --------------------------------------------------------------
    #: Brightness of keys above a bar. Kept well lit: "full brightness" is the
    #: point of this theme, and a dark key reads as a dead LED.
    _BACKDROP = 0.38
    #: Extra backdrop brightness right on a beat, so the whole board thumps.
    _KICK_BACKDROP = 0.45
    _KICK_DECAY_TIME = 0.12
    #: Hue step per beat: about nine beats round the colour wheel.
    _BEAT_HUE_STEP = 0.11
    _HUE_DRIFT = 0.015              # hue turns per second between beats
    _HUE_ACROSS = 0.28              # hue spread from the middle to the edges
    _TIP_WHITENING = 0.5            # how white the top of a bar glows
    _TIP_WIDTH = 0.13

    _WAVE_SPEED = 16.0              # key widths per second
    _WAVE_WIDTH = 1.1
    _WAVE_LIFETIME = 0.7
    _BEAT_WAVE_STRENGTH = 0.85
    _PRESS_WAVE_STRENGTH = 0.45
    _MAX_WAVES = 12

    # -- idle show ----------------------------------------------------------
    _IDLE_BACKDROP = 0.5
    _IDLE_SATURATION = 0.92
    _IDLE_HUE_SPEED = 0.035
    _IDLE_HUE_ACROSS = 0.55
    #: Seconds between heartbeats; each is a "lub" then a softer "dub".
    _HEARTBEAT_PERIOD = 2.6
    _HEARTBEAT_DUB_DELAY = 0.28
    _HEARTBEAT_SPEED = 11.0
    _HEARTBEAT_STRENGTH = 0.8

    #: The spacebar, where beats land.
    _BEAT_ORIGIN = (BOARD_WIDTH_UNITS / 2, KEYBOARD_ROWS - 1)

    def __init__(self):
        self._audio_lock = threading.Lock()
        self._pending_audio: List[AudioLevels] = []
        super().__init__()

    def on_audio_levels(self, levels: AudioLevels) -> None:
        # Called from the audio-reader thread; applied on the next step.
        with self._audio_lock:
            if len(self._pending_audio) >= self._MAX_PENDING_AUDIO:
                self._pending_audio.pop(0)
            self._pending_audio.append(levels)

    @property
    def presence(self) -> float:
        """How much of the board the music owns, 0.0 (idle show) to 1.0."""
        return self._tracker.presence

    # ------------------------------------------------------------ world ---

    def _reset(self) -> None:
        self._tracker = SpectrumTracker()
        self._levels = [0.0] * BAND_COUNT
        self._waves: List[_Wave] = []
        self._kick = 0.0
        self._hue = 0.0
        self._quiet_for = 0.0

    def _apply_press(self, row: int, column: int) -> None:
        self._add_wave(_Wave(physical_x(row, column), row, self._PRESS_WAVE_STRENGTH, 0.5))

    def _step(self, now: float) -> None:
        dt = self.step_seconds
        self._feed_audio(dt)

        if self._tracker.take_beat():
            self._kick = 1.0
            self._hue += self._BEAT_HUE_STEP
            origin_x, origin_row = self._BEAT_ORIGIN
            self._add_wave(_Wave(origin_x, origin_row, self._BEAT_WAVE_STRENGTH, 0.33))

        self._kick *= math.exp(-dt / self._KICK_DECAY_TIME)
        self._hue += self._HUE_DRIFT * dt
        self._levels = self._tracker.levels
        self._age_waves(dt)

    def _feed_audio(self, dt: float) -> None:
        with self._audio_lock:
            windows, self._pending_audio = self._pending_audio, []
        for levels in windows:
            self._tracker.update(levels, self._AUDIO_WINDOW)

        if windows:
            self._quiet_for = 0.0
            return
        self._quiet_for += dt
        if self._quiet_for >= self._AUDIO_STALL_SECONDS:
            self._tracker.decay(dt)

    def _add_wave(self, wave: _Wave) -> None:
        if len(self._waves) >= self._MAX_WAVES:
            self._waves.pop(0)
        self._waves.append(wave)

    def _age_waves(self, dt: float) -> None:
        for wave in self._waves:
            wave.age += dt
        self._waves = [wave for wave in self._waves if wave.age < self._WAVE_LIFETIME]

    # -------------------------------------------------------- rendering ---

    def _render_key(self, row: int, column: int, elapsed: float) -> RGB:
        key_x = physical_x(row, column)
        across = key_x / BOARD_WIDTH_UNITS
        # 0 at the middle of the board, 1 at either edge.
        spread = min(1.0, abs(across - 0.5) * 2)
        height = (KEYBOARD_ROWS - 1 - row) / (KEYBOARD_ROWS - 1)

        presence = self._tracker.presence
        idle = self._idle_color(key_x, row, across, spread, height, elapsed) if presence < 1.0 else None
        if presence <= 0.0:
            return idle
        music = self._music_color(key_x, row, spread, height)
        return music if idle is None else _mix(idle, music, presence)

    def _band_level(self, spread: float) -> float:
        """Level at a point across the board, bass in the middle."""
        position = spread * (BAND_COUNT - 1)
        lower = int(position)
        upper = min(lower + 1, BAND_COUNT - 1)
        blend = position - lower
        return self._levels[lower] + (self._levels[upper] - self._levels[lower]) * blend

    def _music_color(self, key_x: float, row: int, spread: float, height: float) -> RGB:
        bar = self._band_level(spread)
        hue = self._hue + spread * self._HUE_ACROSS + height * 0.06
        fill = _bar_fill(height, bar)

        backdrop = min(1.0, self._BACKDROP + self._KICK_BACKDROP * self._kick)
        color = scale_brightness(_hue_color(hue), backdrop + (1.0 - backdrop) * fill)

        tip = math.exp(-((height - bar) / self._TIP_WIDTH) ** 2) * fill
        color = _mix(color, _WHITE, tip * self._TIP_WHITENING * self._tracker.loudness)

        for wave in self._waves:
            ring = self._ring(key_x, row, wave.x, wave.row, wave.age * self._WAVE_SPEED)
            fade = (1.0 - wave.age / self._WAVE_LIFETIME) ** 1.5
            amount = ring * fade * wave.strength
            if amount > 0.02:
                color = _add_light(color, _hue_color(hue + wave.hue_shift, 0.55), amount)
        return color

    def _idle_color(self, key_x: float, row: int, across: float, spread: float,
                    height: float, elapsed: float) -> RGB:
        """
        A phantom equalizer: two slow waves stand in for the music, so the
        board already looks like what sound will do to it.
        """
        bar = (
            0.45
            + 0.22 * math.sin(elapsed * 0.9 + spread * 4.0)
            + 0.14 * math.sin(elapsed * 2.3 - across * 9.0 + 1.3)
        )
        hue = elapsed * self._IDLE_HUE_SPEED + across * self._IDLE_HUE_ACROSS + height * 0.08
        fill = _bar_fill(height, bar)
        color = scale_brightness(
            _hue_color(hue, self._IDLE_SATURATION),
            self._IDLE_BACKDROP + (1.0 - self._IDLE_BACKDROP) * fill,
        )

        beat_age = elapsed % self._HEARTBEAT_PERIOD
        origin_x, origin_row = self._BEAT_ORIGIN
        for age, strength in ((beat_age, 1.0), (beat_age - self._HEARTBEAT_DUB_DELAY, 0.6)):
            if not 0.0 <= age < self._WAVE_LIFETIME:
                continue
            ring = self._ring(key_x, row, origin_x, origin_row, age * self._HEARTBEAT_SPEED)
            fade = (1.0 - age / self._WAVE_LIFETIME) ** 1.5
            color = _add_light(color, _hue_color(hue + 0.33, 0.45),
                               ring * fade * strength * self._HEARTBEAT_STRENGTH)
        return color

    def _ring(self, key_x: float, row: int, origin_x: float, origin_row: float,
              radius: float) -> float:
        """Brightness of a key under a ring of `radius` keys around an origin."""
        distance = math.hypot(key_x - origin_x, row - origin_row)
        offset = (distance - radius) / self._WAVE_WIDTH
        return math.exp(-offset * offset)
