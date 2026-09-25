"""
Hardware-free tests for the layout, theme maths and frame packing.

These run anywhere, which matters because opening the keyboard needs an OS
permission grant that CI (and a fresh macOS machine) will not have.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from f87pro.layout import (
    BOARD_WIDTH_UNITS,
    KEY_POSITIONS,
    LED_COUNT,
    PIXEL_COLUMNS,
    ROWS,
    physical_x,
    pixel_columns,
)
from f87pro.themes import (
    THEMES,
    BrightnessAdjusted,
    KEYBOARD_COLUMNS,
    KEYBOARD_ROWS,
    get_theme,
    hex_to_rgb,
    is_static,
    render_text_bitmap,
    sample_palette,
    sample_ramp,
    scale_brightness,
)

SAMPLE_TIMES = (0.0, 0.7, 3.3, 12.5, 90.0)


# ----------------------------------------------------------------- layout ---

def test_every_key_position_is_inside_the_grid():
    for led, (row, column) in KEY_POSITIONS.items():
        assert 0 <= row < KEYBOARD_ROWS, f"LED {led} row out of range"
        assert 0 <= column < KEYBOARD_COLUMNS, f"LED {led} column out of range"
        assert 0 <= led < LED_COUNT, f"LED {led} outside the LED buffer"


def test_key_positions_are_unique():
    positions = list(KEY_POSITIONS.values())
    assert len(positions) == len(set(positions)), "two LEDs share a position"


def test_rows_cover_every_mapped_key_exactly_once():
    flattened = [led for row in ROWS for led in row]
    assert sorted(flattened) == sorted(KEY_POSITIONS)


def test_rows_are_ordered_left_to_right():
    for row in ROWS:
        columns = [KEY_POSITIONS[led][1] for led in row]
        assert columns == sorted(columns)


def test_physical_positions_increase_left_to_right_within_the_board():
    for row in ROWS:
        centers = [physical_x(*KEY_POSITIONS[led]) for led in row]
        assert centers == sorted(centers)
        assert 0.0 < centers[0] and centers[-1] < BOARD_WIDTH_UNITS


def test_each_text_pixel_belongs_to_at_most_one_key_per_row():
    for row_index, row in enumerate(ROWS):
        owned = [pixel for led in row for pixel in pixel_columns(*KEY_POSITIONS[led])]
        assert len(owned) == len(set(owned)), f"row {row_index} shares a pixel"
        assert all(0 <= pixel < PIXEL_COLUMNS for pixel in owned)


# ---------------------------------------------------------- colour helpers ---

def test_hex_to_rgb_handles_both_notations():
    assert hex_to_rgb("#ff8000") == (255, 128, 0)
    assert hex_to_rgb("ff8000") == (255, 128, 0)


def test_sample_palette_wraps_without_a_seam():
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    assert sample_palette(palette, 0.0) == sample_palette(palette, 1.0)
    assert sample_palette(palette, 0.5) == sample_palette(palette, 2.5)


def test_sample_ramp_clamps_to_its_endpoints():
    ramp = [(0, 0, 0), (255, 255, 255)]
    assert sample_ramp(ramp, -5.0) == (0, 0, 0)
    assert sample_ramp(ramp, 0.0) == (0, 0, 0)
    assert sample_ramp(ramp, 1.0) == (255, 255, 255)
    assert sample_ramp(ramp, 9.0) == (255, 255, 255)


def test_scale_brightness_clamps_both_ends():
    assert scale_brightness((200, 100, 50), 0.0) == (0, 0, 0)
    assert scale_brightness((200, 100, 50), 10.0) == (255, 255, 255)


# ----------------------------------------------------------------- themes ---

@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_theme_output_is_always_a_valid_colour(theme_name):
    theme = THEMES[theme_name]
    for elapsed in SAMPLE_TIMES:
        for row in range(KEYBOARD_ROWS):
            for column in range(KEYBOARD_COLUMNS):
                color = theme.color_at(row, column, elapsed)
                assert len(color) == 3
                for channel in color:
                    assert isinstance(channel, int)
                    assert 0 <= channel <= 255


@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_no_mapped_key_is_ever_completely_dark(theme_name):
    """A fully black key looks like a broken LED on a physical board."""
    theme = THEMES[theme_name]
    if theme.allows_dark_keys:
        pytest.skip("unlit keys are part of this theme's design")
    for elapsed in SAMPLE_TIMES:
        for led, (row, column) in KEY_POSITIONS.items():
            color = theme.color_at(row, column, elapsed)
            assert sum(color) > 0, f"{theme_name}: LED {led} went black at t={elapsed}"


@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_animated_themes_actually_change_over_time(theme_name):
    theme = THEMES[theme_name]
    first = [theme.color_at(r, c, 0.0) for r, c in KEY_POSITIONS.values()]
    later = [theme.color_at(r, c, 4.0) for r, c in KEY_POSITIONS.values()]
    if is_static(theme):
        assert first == later
    else:
        assert first != later


def test_text_bitmap_is_rectangular_and_case_insensitive():
    bitmap = render_text_bitmap("rojan")
    assert bitmap == render_text_bitmap("ROJAN")
    assert len({len(row) for row in bitmap}) == 1
    assert len(bitmap[0]) <= PIXEL_COLUMNS, "ROJAN must fit the board without scrolling"


def test_rojan_is_a_still_name_on_an_otherwise_unlit_board():
    theme = get_theme("rojan")
    assert is_static(theme)

    colors = [theme.color_at(r, c, 0.0) for r, c in KEY_POSITIONS.values()]
    lit = [color for color in colors if sum(color) > 0]
    assert lit, "the name must light some keys"
    assert len(lit) < len(colors), "keys outside the name must stay unlit"
    # The spacebar row is never part of the lettering.
    assert all(sum(theme.color_at(5, c, 0.0)) == 0 for c in range(KEYBOARD_COLUMNS))


def test_reactor_keeps_moving_with_no_keystrokes():
    """It must look struck several times a second even when nobody types."""
    theme = get_theme("reactor")
    positions = list(KEY_POSITIONS.values())
    frames = [[theme.color_at(r, c, step * 0.1) for r, c in positions] for step in range(10)]
    assert all(earlier != later for earlier, later in zip(frames, frames[1:]))


def test_brightness_wrapper_carries_reactive_settings():
    reactor = get_theme("reactor")
    dimmed = BrightnessAdjusted(reactor, 0.5)
    assert dimmed.reactive_surge == reactor.reactive_surge
    assert dimmed.reactive_bubble_radius == reactor.reactive_bubble_radius
    assert BrightnessAdjusted(get_theme("rojan"), 0.5).allows_dark_keys


def test_get_theme_is_case_insensitive_and_rejects_unknown_names():
    assert get_theme("AURORA") is get_theme("aurora")
    with pytest.raises(ValueError, match="Unknown theme"):
        get_theme("definitely-not-a-theme")


def test_brightness_wrapper_dims_without_changing_identity():
    theme = get_theme("spectrum")
    dimmed = BrightnessAdjusted(theme, 0.5)

    assert dimmed.name == theme.name
    assert dimmed.frames_per_second == theme.frames_per_second

    full = theme.color_at(2, 5, 1.0)
    half = dimmed.color_at(2, 5, 1.0)
    assert sum(half) < sum(full)


def test_brightness_wrapper_preserves_static_flag():
    assert is_static(BrightnessAdjusted(get_theme("dusk"), 0.4))
    assert not is_static(BrightnessAdjusted(get_theme("aurora"), 0.4))
