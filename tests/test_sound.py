"""Hardware-free tests for the sound-reactive `pulse` theme and its tracker."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from f87pro.audio import BAND_COUNT, AudioLevels, SpectrumTracker, parse_levels_line
from f87pro.layout import KEY_POSITIONS
from f87pro.sound import PulseTheme
from f87pro.themes import THEMES, BrightnessAdjusted

WINDOW = 1 / 60


def _levels(loudness, bass=None, rest=None):
    """Levels with the three bass bands at `bass` and the others at `rest`."""
    bass = loudness if bass is None else bass
    rest = loudness if rest is None else rest
    return AudioLevels(loudness, (bass,) * 3 + (rest,) * (BAND_COUNT - 3))


def _frame(theme, elapsed):
    return [theme.color_at(r, c, elapsed) for r, c in KEY_POSITIONS.values()]


def _feed(theme, levels, start, seconds):
    """Play `levels` into the theme for `seconds`, one window per frame."""
    elapsed = start
    while elapsed < start + seconds:
        theme.on_audio_levels(levels)
        elapsed += WINDOW
        theme.color_at(0, 0, elapsed)
    return elapsed


# ------------------------------------------------------------ helper I/O ---

def test_helper_lines_parse_into_levels():
    line = " ".join(["0.25"] + ["0.1"] * BAND_COUNT)
    levels = parse_levels_line(line)
    assert levels.loudness == 0.25
    assert levels.bands == (0.1,) * BAND_COUNT


def test_malformed_helper_lines_are_skipped():
    assert parse_levels_line("") is None
    assert parse_levels_line("0.1 0.2") is None
    assert parse_levels_line("error: nope") is None


# ---------------------------------------------------------------- tracker ---

def test_quiet_and_loud_audio_both_fill_the_bars():
    for volume in (0.01, 0.4):
        tracker = SpectrumTracker()
        for _ in range(120):
            tracker.update(_levels(volume), WINDOW)
        assert min(tracker.levels) > 0.9, f"volume {volume} should fill the board"


def test_presence_rises_with_sound_and_falls_after_silence():
    tracker = SpectrumTracker()
    assert tracker.presence == 0.0
    for _ in range(90):
        tracker.update(_levels(0.2), WINDOW)
    assert tracker.presence > 0.9

    # A short gap, like the pause between two songs' notes, keeps the music.
    for _ in range(30):
        tracker.update(_levels(0.0), WINDOW)
    assert tracker.presence > 0.9

    for _ in range(360):
        tracker.update(_levels(0.0), WINDOW)
    assert tracker.presence < 0.1


def test_a_kick_drum_pattern_is_counted_beat_for_beat():
    tracker = SpectrumTracker()
    beats = 0
    # 120 BPM for 4 seconds: a 3-window kick every half second over quiet bass.
    for window in range(240):
        kicking = window % 30 < 3
        tracker.update(_levels(0.2, bass=0.5 if kicking else 0.05, rest=0.1), WINDOW)
        beats += tracker.take_beat()
    assert 7 <= beats <= 8


def test_a_steady_tone_is_not_a_beat():
    tracker = SpectrumTracker()
    for _ in range(30):
        tracker.update(_levels(0.2), WINDOW)
    tracker.take_beat()  # the tone starting is fine to count once
    beats = 0
    for _ in range(240):
        tracker.update(_levels(0.2), WINDOW)
        beats += tracker.take_beat()
    assert beats == 0


# ------------------------------------------------------------------ theme ---

def test_pulse_is_registered_and_asks_for_audio():
    assert "pulse" in THEMES
    assert THEMES["pulse"].listens_to_audio


def test_without_audio_it_plays_a_bright_lit_idle_show():
    theme = PulseTheme()
    first, later = _frame(theme, 0.5), _frame(theme, 1.7)
    assert theme.presence == 0.0
    assert first != later, "the idle show must move"
    for frame in (first, later):
        assert all(max(color) > 0 for color in frame), "no key may go dark"
        assert sum(max(color) for color in frame) / len(frame) > 140


def test_music_takes_over_the_board_then_hands_back():
    theme = PulseTheme()
    elapsed = _feed(theme, _levels(0.3), 0.0, 2.0)
    assert theme.presence > 0.9
    music = _frame(theme, elapsed)

    elapsed = _feed(theme, _levels(0.0), elapsed, 6.0)
    assert theme.presence < 0.1
    assert _frame(theme, elapsed) != music


def test_louder_bands_light_more_keys():
    loud, quiet = PulseTheme(), PulseTheme()
    elapsed = _feed(loud, _levels(0.3), 0.0, 2.0)
    _feed(quiet, _levels(0.3), 0.0, 2.0)
    # Same history, then the quiet one drops to a whisper relative to its peak.
    end = _feed(loud, _levels(0.3), elapsed, 0.5)
    _feed(quiet, _levels(0.02), elapsed, 0.5)
    total = lambda frame: sum(sum(color) for color in frame)
    assert total(_frame(loud, end)) > total(_frame(quiet, end))


def test_a_beat_sends_a_wave_and_moves_the_colours():
    theme = PulseTheme()
    elapsed = _feed(theme, _levels(0.2, bass=0.05, rest=0.1), 0.0, 1.0)
    hue = theme._hue
    elapsed = _feed(theme, _levels(0.3, bass=0.6, rest=0.1), elapsed, WINDOW * 2)
    assert theme._waves, "a kick must send a wave"
    assert theme._hue > hue + 0.1


def test_every_frame_is_valid_rgb_while_music_plays():
    theme = PulseTheme()
    elapsed = 0.0
    for window in range(180):
        kicking = window % 25 < 2
        theme.on_audio_levels(_levels(0.3, bass=0.7 if kicking else 0.1, rest=0.2))
        elapsed += WINDOW
        for color in _frame(theme, elapsed):
            assert all(0 <= channel <= 255 for channel in color)
            assert max(color) > 0


def test_brightness_wrapper_passes_audio_through():
    theme = PulseTheme()
    wrapped = BrightnessAdjusted(theme, 0.5)
    assert wrapped.listens_to_audio
    wrapped.on_audio_levels(_levels(0.3))
    assert theme._pending_audio
