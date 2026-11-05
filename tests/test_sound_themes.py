"""Hardware-free tests for the sound themes built on `AudioTheme`."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from f87pro.audio import BAND_COUNT, AudioLevels
from f87pro.layout import KEY_POSITIONS
from f87pro.sound_themes import BlazeTheme, CoreTheme, MonsoonTheme, WaterfallTheme
from f87pro.themes import THEMES

WINDOW = 1 / 60
SOUND_THEMES = (BlazeTheme, WaterfallTheme, MonsoonTheme, CoreTheme)


def _levels(loudness, bass=None, rest=None):
    bass = loudness if bass is None else bass
    rest = loudness if rest is None else rest
    return AudioLevels(loudness, (bass,) * 3 + (rest,) * (BAND_COUNT - 3))


def _frame(theme, elapsed):
    return [theme.color_at(r, c, elapsed) for r, c in KEY_POSITIONS.values()]


def _feed(theme, levels, start, seconds):
    elapsed = start
    while elapsed < start + seconds:
        theme.on_audio_levels(levels)
        elapsed += WINDOW
        theme.color_at(0, 0, elapsed)
    return elapsed


def _brightness(frame):
    return sum(sum(color) for color in frame)


@pytest.mark.parametrize("cls", SOUND_THEMES)
def test_registered_and_listening(cls):
    assert THEMES[cls.name].listens_to_audio


@pytest.mark.parametrize("cls", SOUND_THEMES)
def test_idle_show_moves_and_stays_lit(cls):
    theme = cls()
    first, later = _frame(theme, 0.5), _frame(theme, 2.1)
    assert theme.presence == 0.0
    assert first != later
    for frame in (first, later):
        assert all(max(color) > 0 for color in frame)


@pytest.mark.parametrize("cls", SOUND_THEMES)
def test_music_takes_over_and_every_frame_is_valid(cls):
    theme = cls()
    elapsed = 0.0
    for window in range(150):
        kicking = window % 25 < 2
        theme.on_audio_levels(_levels(0.3, bass=0.7 if kicking else 0.1, rest=0.2))
        elapsed += WINDOW
        for color in _frame(theme, elapsed):
            assert all(0 <= channel <= 255 for channel in color)
            assert max(color) > 0
    assert theme.presence > 0.9


@pytest.mark.parametrize("cls", SOUND_THEMES)
def test_silence_hands_the_board_back(cls):
    theme = cls()
    elapsed = _feed(theme, _levels(0.3), 0.0, 2.0)
    elapsed = _feed(theme, _levels(0.0), elapsed, 6.0)
    assert theme.presence < 0.1


@pytest.mark.parametrize("cls", (BlazeTheme, CoreTheme))
def test_louder_bass_lights_more_of_the_board(cls):
    loud, quiet = cls(), cls()
    elapsed = _feed(loud, _levels(0.3), 0.0, 2.0)
    _feed(quiet, _levels(0.3), 0.0, 2.0)
    end = _feed(loud, _levels(0.3), elapsed, 0.5)
    _feed(quiet, _levels(0.02), elapsed, 0.5)
    assert _brightness(_frame(loud, end)) > _brightness(_frame(quiet, end))


def test_blaze_beats_throw_sparks():
    theme = BlazeTheme()
    elapsed = _feed(theme, _levels(0.2, bass=0.05, rest=0.1), 0.0, 1.0)
    sparks = len(theme._sparks)
    _feed(theme, _levels(0.3, bass=0.6, rest=0.1), elapsed, WINDOW * 2)
    assert len(theme._sparks) >= sparks + BlazeTheme._BEAT_SPARKS


def test_blaze_never_leaves_fire_colours_when_idle():
    # Feedback on forge: idle must stay in the warm palette, never cold.
    theme = BlazeTheme()
    for elapsed in (0.5, 3.0, 9.0):
        for red, green, blue in _frame(theme, elapsed):
            assert red >= blue


def test_waterfall_scrolls_sound_from_right_to_left():
    theme = WaterfallTheme()
    elapsed = _feed(theme, _levels(0.0), 0.0, 3.0)
    # A burst of treble lands on the right of the top row...
    elapsed = _feed(theme, AudioLevels(0.3, (0.0,) * 10 + (0.8, 0.8)), elapsed, 0.15)
    right_now = theme._history[-1][0]
    elapsed = _feed(theme, _levels(0.0), elapsed, 0.6)
    # ...and some columns later it has moved left.
    columns_moved = round(0.6 / WaterfallTheme._SCROLL_INTERVAL)
    assert right_now > 0.5
    assert theme._history[-1 - columns_moved][0] == pytest.approx(right_now, abs=1e-9)


def test_monsoon_rains_harder_with_more_treble():
    def drops_after(treble):
        theme = MonsoonTheme()
        _feed(theme, AudioLevels(0.3, (0.3,) * 8 + (treble,) * 4), 0.0, 1.5)
        return len(theme._drops)
    assert drops_after(0.5) > drops_after(0.02)


def test_core_heats_up_under_sustained_loud_music():
    theme = CoreTheme()
    start = theme._temperature
    _feed(theme, _levels(0.4), 0.0, 6.0)
    assert theme._temperature > start + 0.4


@pytest.mark.parametrize("cls", SOUND_THEMES)
def test_key_presses_show_up(cls):
    pressed, plain = cls(), cls()
    _frame(pressed, 1.0), _frame(plain, 1.0)
    pressed.on_key_press(3, 5)
    assert _frame(pressed, 1.0 + WINDOW * 2) != _frame(plain, 1.0 + WINDOW * 2)


def _hue_families(frame):
    """Distinct colour families in a frame: hues in 12 buckets, greys ignored."""
    import colorsys
    families = set()
    for red, green, blue in frame:
        hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        if saturation > 0.3 and value > 0.1:
            families.add(int(hue * 12) % 12)
    return families


def test_core_shows_many_colours_at_once():
    idle = CoreTheme()
    assert len(_hue_families(_frame(idle, 1.0))) >= 6

    music = CoreTheme()
    elapsed = _feed(music, _levels(0.3, bass=0.6, rest=0.3), 0.0, 3.0)
    assert len(_hue_families(_frame(music, elapsed))) >= 6


def test_core_beats_turn_the_colour_wheel():
    theme = CoreTheme()
    elapsed = _feed(theme, _levels(0.2, bass=0.05, rest=0.1), 0.0, 1.0)
    hue = theme._hue
    _feed(theme, _levels(0.3, bass=0.6, rest=0.1), elapsed, WINDOW * 2)
    assert theme._hue >= hue + CoreTheme._BEAT_HUE_STEP
