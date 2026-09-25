"""Tests for turning a theme into the flat RGB buffer the keyboard expects."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from f87pro.device import AulaF87Pro
from f87pro.layout import KEY_POSITIONS, LED_COUNT
from f87pro.themes import THEMES, get_theme


@pytest.fixture
def keyboard():
    """A device object that is never connected -- frame packing needs no HID."""
    return AulaF87Pro()


def test_frame_has_three_channels_per_led(keyboard):
    frame = keyboard.render_theme_frame(get_theme("aurora"), 1.0)
    assert len(frame) == LED_COUNT * 3


@pytest.mark.parametrize("theme_name", sorted(THEMES))
def test_frame_channels_are_in_range(keyboard, theme_name):
    frame = keyboard.render_theme_frame(THEMES[theme_name], 2.0)
    assert all(0 <= channel <= 255 for channel in frame)


def test_only_mapped_leds_are_lit(keyboard):
    """The board reports 102 LED slots but only 87 sit under a key."""
    frame = keyboard.render_theme_frame(get_theme("spectrum"), 0.5)
    lit = {led for led in range(LED_COUNT)
           if any(frame[led * 3:led * 3 + 3])}
    assert lit == set(KEY_POSITIONS)


def test_frame_matches_the_theme_for_a_known_key(keyboard):
    theme = get_theme("dusk")
    frame = keyboard.render_theme_frame(theme, 0.0)

    escape_led = 0
    row, column = KEY_POSITIONS[escape_led]
    assert tuple(frame[0:3]) == theme.color_at(row, column, 0.0)


def test_bubble_triggered_just_after_a_frame_is_not_discarded():
    """
    The listener thread fires between frames, so a bubble's start time can be
    marginally ahead of the timestamp the current frame is rendered at. It is
    pending, not expired, and must still be drawn.
    """
    from f87pro.reactive import BubbleField

    field = BubbleField()
    now = 1000.0
    field.trigger(27, now + 0.005)      # arrives just after this frame's clock

    field.render([0] * (LED_COUNT * 3), now)          # must not prune it
    later = field.render([0] * (LED_COUNT * 3), now + 0.1)

    assert any(later), "bubble was dropped before it ever rendered"


def test_expired_bubbles_are_pruned():
    from f87pro.reactive import BubbleField, BUBBLE_LIFETIME

    field = BubbleField()
    now = 1000.0
    field.trigger(27, now)
    field.render([0] * (LED_COUNT * 3), now + BUBBLE_LIFETIME + 0.1)
    assert len(field._bubbles) == 0


def test_successive_bubbles_get_different_colours():
    """Consecutive keystrokes must be tellable apart at a glance."""
    from f87pro.reactive import BubbleField, BUBBLE_COLORS

    field = BubbleField()
    for index, led in enumerate([27, 21, 15, 9]):
        field.trigger(led, 1000.0 + index * 0.1)

    issued = [color for _, _, color in field._bubbles]
    assert len(set(issued)) == len(issued), "two concurrent bubbles share a colour"
    assert issued == BUBBLE_COLORS[:4]


def test_colour_cycle_wraps():
    from f87pro.reactive import BubbleField, BUBBLE_COLORS

    field = BubbleField()
    count = len(BUBBLE_COLORS)
    for index in range(count + 1):
        field.trigger(27 if index % 2 else 21, 1000.0 + index)

    assert field._next_color == count + 1


def test_repeat_on_a_held_key_keeps_its_colour():
    """A key repeat restarts its wave; it must not burn the next colour."""
    from f87pro.reactive import BubbleField

    field = BubbleField()
    field.trigger(27, 1000.0)
    first = field._bubbles[0][2]
    field.trigger(27, 1000.01)          # within the retrigger window

    assert len(field._bubbles) == 1
    assert field._bubbles[0][2] == first
    assert field._next_color == 1


def test_typing_energy_builds_with_keystrokes_and_drains_after():
    from f87pro.reactive import BubbleField

    field = BubbleField()
    assert field.energy(now=100.0) == 0.0

    field.trigger(9, when=100.0)
    one_key = field.energy(now=100.0)
    for offset, led in enumerate((15, 21, 27, 33)):
        field.trigger(led, when=100.0 + offset * 0.01)
    burst = field.energy(now=100.05)

    assert 0.0 < one_key < burst <= 1.0
    assert field.energy(now=100.9) < burst
