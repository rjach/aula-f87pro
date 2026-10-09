"""
System audio input for sound-reactive themes.

Two parts with separate jobs:

- `SystemAudioListener` gets raw levels out of the OS. On macOS it compiles a
  small Swift helper (`audio_tap.swift`) once, runs it, and reads one line of
  band levels per ~16 ms from its stdout. No audio is recorded: the helper
  reduces each window to a handful of numbers and drops the samples.
- `SpectrumTracker` turns those raw levels into what a theme can draw: bands
  scaled to 0-1 whatever the system volume is, a beat flag, and how sure we
  are that something is playing at all.

The tracker is pure maths, so it is tested without any audio hardware.
"""
import hashlib
import math
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

#: Bands the Swift helper reports, bass first. Must match `bandCenters` there.
BAND_COUNT = 12

_HELPER_SOURCE = Path(__file__).with_name("audio_tap.swift")
_HELPER_CACHE_DIR = Path.home() / "Library" / "Caches" / "aula-f87pro"
_COMPILE_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class AudioLevels:
    """One window of raw audio levels, as RMS amplitudes."""

    loudness: float
    bands: Tuple[float, ...]


def parse_levels_line(line: str) -> Optional[AudioLevels]:
    """
    Parse one line of the helper's output.

    @param line - "<loudness> <band 0> ... <band N-1>".
    @returns The levels, or None for a malformed line.
    """
    try:
        values = [float(token) for token in line.split()]
    except ValueError:
        return None
    if len(values) != BAND_COUNT + 1:
        return None
    return AudioLevels(loudness=values[0], bands=tuple(values[1:]))


# --------------------------------------------------------------------------
# Tracker
# --------------------------------------------------------------------------

class SpectrumTracker:
    """
    Makes raw levels drawable: volume-independent, smoothed, with beats.

    Each band is divided by its own slowly-decaying peak, so a quiet track and
    a loud one both fill the board. That peak never drops below a share of
    the loudest band, or a near-empty treble band would be blown up into noise.
    """

    #: RMS below this counts as silence (about -54 dBFS): system hiss and a
    #: paused player both sit under it.
    SILENCE_LEVEL = 0.002
    #: Seconds of sound before the board fully commits to the music.
    _PRESENCE_RISE_TIME = 0.35
    #: Seconds of silence tolerated before the idle show starts returning, so
    #: a quiet bar or the gap between tracks does not flicker the show back.
    _SILENCE_GRACE = 1.5
    _PRESENCE_FALL_TIME = 0.9

    #: Seconds for a band's reference peak to decay to ~37%. Long enough that a
    #: chorus stays big after the verse, short enough to adapt to a new track.
    _PEAK_DECAY_TIME = 4.0
    #: A band's peak is at least this share of the loudest band's peak.
    _PEAK_FLOOR_SHARE = 0.18
    #: Bars jump up instantly and fall back over this many seconds.
    _RELEASE_TIME = 0.16
    #: Softens the response so mid-level sound still lifts the bars well.
    _LEVEL_CURVE = 0.75

    #: Bass bands used for beat detection.
    _BEAT_BANDS = (0, 1, 2)
    #: A beat is bass this many times above its recent average...
    _BEAT_RATIO = 1.45
    #: ...and at least this share of its own peak, so soft rumbles don't count.
    _BEAT_MIN_SHARE = 0.35
    _BEAT_AVERAGE_TIME = 0.45
    #: Shortest gap between beats (~330 BPM), so one kick is not counted twice.
    _BEAT_REFRACTORY = 0.18

    def __init__(self):
        self._peaks = [self.SILENCE_LEVEL] * BAND_COUNT
        self._levels = [0.0] * BAND_COUNT
        self._loudness = 0.0
        self._presence = 0.0
        self._silent_for = math.inf
        self._bass_average = 0.0
        self._since_beat = math.inf
        self._beat_pending = False

    @property
    def levels(self) -> List[float]:
        """Per-band level, 0.0-1.0, bass first."""
        return list(self._levels)

    @property
    def loudness(self) -> float:
        """Overall level, 0.0-1.0, relative to the recent peak."""
        return self._loudness

    @property
    def presence(self) -> float:
        """0.0 when nothing is playing, rising to 1.0 while sound continues."""
        return self._presence

    def take_beat(self) -> bool:
        """
        Whether a beat landed since the last call. Clears the flag.

        @returns True once per detected beat.
        """
        beat, self._beat_pending = self._beat_pending, False
        return beat

    def update(self, levels: AudioLevels, dt: float) -> None:
        """
        Fold one window of raw levels into the tracked state.

        @param levels - Raw levels from the listener.
        @param dt - Seconds this window covers.
        """
        self._track_presence(levels.loudness, dt)
        self._track_bands(levels.bands, dt)
        self._track_beat(levels.bands, dt)

    def decay(self, dt: float) -> None:
        """
        Advance time with no audio arriving, e.g. the listener failed or the
        stream stalled. Everything falls back toward the idle state.

        @param dt - Seconds elapsed.
        """
        self.update(AudioLevels(0.0, (0.0,) * BAND_COUNT), dt)

    def _track_presence(self, loudness: float, dt: float) -> None:
        if loudness >= self.SILENCE_LEVEL:
            self._silent_for = 0.0
            target, time_constant = 1.0, self._PRESENCE_RISE_TIME
        else:
            self._silent_for += dt
            if self._silent_for < self._SILENCE_GRACE:
                return
            target, time_constant = 0.0, self._PRESENCE_FALL_TIME
        blend = 1.0 - math.exp(-dt / time_constant)
        self._presence += (target - self._presence) * blend

    def _track_bands(self, bands: Tuple[float, ...], dt: float) -> None:
        peak_decay = math.exp(-dt / self._PEAK_DECAY_TIME)
        release = math.exp(-dt / self._RELEASE_TIME)
        for index, value in enumerate(bands):
            self._peaks[index] = max(value, self._peaks[index] * peak_decay, self.SILENCE_LEVEL)
        floor = max(self._peaks) * self._PEAK_FLOOR_SHARE

        total = 0.0
        for index, value in enumerate(bands):
            reference = max(self._peaks[index], floor)
            target = min(1.0, value / reference) ** self._LEVEL_CURVE
            self._levels[index] = max(target, self._levels[index] * release)
            total += self._levels[index]
        self._loudness = total / len(bands)

    def _track_beat(self, bands: Tuple[float, ...], dt: float) -> None:
        bass = sum(bands[index] for index in self._BEAT_BANDS)
        bass_peak = sum(self._peaks[index] for index in self._BEAT_BANDS)
        self._since_beat += dt

        is_onset = (
            bass > self._bass_average * self._BEAT_RATIO
            and bass > bass_peak * self._BEAT_MIN_SHARE
            and self._since_beat >= self._BEAT_REFRACTORY
        )
        if is_onset:
            self._beat_pending = True
            self._since_beat = 0.0

        blend = 1.0 - math.exp(-dt / self._BEAT_AVERAGE_TIME)
        self._bass_average += (bass - self._bass_average) * blend


# --------------------------------------------------------------------------
# Listener
# --------------------------------------------------------------------------

class SystemAudioListener:
    """
    Streams system audio levels from the Swift helper to a callback.

    `start` returns False with a readable `failure` when capture is not
    possible up front (not macOS, no compiler). Permission problems only show
    once the helper runs, so they arrive asynchronously: the callback simply
    never fires, `failure` is set, and themes keep showing their idle look.
    """

    def __init__(self, on_levels: Callable[[AudioLevels], None],
                 on_failure: Optional[Callable[[str], None]] = None):
        """
        @param on_levels - Called from a background thread for every window.
        @param on_failure - Called once, from a background thread, if the
            helper exits with an error after starting.
        """
        self._on_levels = on_levels
        self._on_failure = on_failure
        self._process: Optional[subprocess.Popen] = None
        self._stopping = False
        #: Set once the helper either delivers audio or exits.
        self._settled = threading.Event()
        self.failure: Optional[str] = None

    def start(self) -> bool:
        """
        Compile the helper if needed and begin streaming.

        @returns True when the helper is running.
        """
        if sys.platform != "darwin":
            self.failure = "system audio capture is only supported on macOS"
            return False

        helper = self._helper_binary()
        if helper is None:
            return False

        try:
            self._process = subprocess.Popen(
                [str(helper)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, text=True, bufsize=1,
            )
        except OSError as error:
            self.failure = f"could not start the audio helper {helper}: {error}"
            return False

        threading.Thread(target=self._read_levels, daemon=True).start()
        return True

    def wait_until_settled(self, timeout: float) -> bool:
        """
        Wait until the helper delivers its first audio or exits, so callers
        can report a missing permission up front instead of mid-animation.

        @param timeout - Most seconds to wait; a helper still quiet after
            this is assumed to be running.
        @returns True unless the helper has already failed.
        """
        self._settled.wait(timeout)
        return self.failure is None

    def stop(self) -> None:
        """Stop the helper. Safe to call more than once."""
        self._stopping = True
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def _read_levels(self) -> None:
        process = self._process
        for line in process.stdout:
            levels = parse_levels_line(line)
            if levels is not None:
                self._settled.set()
                self._on_levels(levels)

        error_text = process.stderr.read().strip()
        process.wait()
        if self._stopping:
            return
        self.failure = error_text.removeprefix("error: ") or (
            f"the audio helper exited with code {process.returncode}"
        )
        self._settled.set()
        if self._on_failure:
            self._on_failure(self.failure)

    def _helper_binary(self) -> Optional[Path]:
        """
        Path to the compiled helper, compiling it on first use.

        The binary is named after a hash of the source, so editing the Swift
        file triggers a rebuild and stale binaries are never run.
        """
        source = _HELPER_SOURCE.read_bytes()
        digest = hashlib.sha256(source).hexdigest()[:12]
        binary = _HELPER_CACHE_DIR / f"audio-tap-{digest}"
        if binary.exists():
            return binary

        compiler = shutil.which("swiftc")
        if compiler is None:
            self.failure = ("swiftc not found, which is needed to build the audio "
                            "helper. Install it with: xcode-select --install")
            return None

        print("Building the system audio helper (first run only)...")
        _HELPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        partial = binary.with_suffix(".partial")
        try:
            result = subprocess.run(
                [compiler, "-O", str(_HELPER_SOURCE), "-o", str(partial)],
                capture_output=True, text=True, timeout=_COMPILE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            self.failure = f"building the audio helper took over {_COMPILE_TIMEOUT_SECONDS}s"
            return None
        if result.returncode != 0:
            detail = (result.stderr.strip().splitlines() or ["no compiler output"])[-1]
            self.failure = f"could not build the audio helper from {_HELPER_SOURCE}: {detail}"
            return None
        partial.replace(binary)
        return binary
