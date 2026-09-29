"""Hardware-free tests for stateful simulation themes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from f87pro.layout import KEY_POSITIONS, PIXEL_COLUMNS
from f87pro.simulation import SandfallTheme, _Grain
from f87pro.themes import KEYBOARD_ROWS, BrightnessAdjusted

STEP = SandfallTheme.step_seconds
# Q sits on the tab row, well away from the edges.
Q_ROW, Q_COLUMN = 2, 1


def _frame(theme, elapsed):
    return [theme.color_at(r, c, elapsed) for r, c in KEY_POSITIONS.values()]


def _quiet_sandfall():
    """A sandfall that never drops grains on its own, so presses are isolated."""
    theme = SandfallTheme()
    theme._AMBIENT_INTERVAL = 10_000.0
    theme._next_ambient = 10_000.0
    return theme


def _grain_count(theme):
    return sum(cell is not None for row in theme._cells for cell in row)


def test_a_key_press_drops_a_grain_that_falls_to_the_bottom():
    theme = _quiet_sandfall()
    theme.color_at(0, 0, 0.0)
    theme.on_key_press(Q_ROW, Q_COLUMN)

    theme.color_at(0, 0, STEP)
    assert _grain_count(theme) == 1
    # One step to spawn at the tab row and fall one row.
    assert any(theme._cells[Q_ROW + 1])

    theme.color_at(0, 0, STEP * 10)
    assert _grain_count(theme) == 1
    assert any(theme._cells[KEYBOARD_ROWS - 1]), "the grain must come to rest on the bottom row"


def test_grains_pile_up_rather_than_overlap():
    theme = _quiet_sandfall()
    theme.color_at(0, 0, 0.0)
    for _ in range(5):
        theme.on_key_press(Q_ROW, Q_COLUMN)
    theme.color_at(0, 0, STEP * 30)
    assert _grain_count(theme) == 5


def test_a_full_bottom_row_flashes_then_clears():
    theme = _quiet_sandfall()
    theme.color_at(0, 0, 0.0)
    theme._cells[-1] = [_Grain((200, 100, 0)) for _ in range(PIXEL_COLUMNS)]
    theme._cells[-2][3] = _Grain((0, 100, 200))

    theme.color_at(0, 0, STEP)
    assert theme._flash_remaining, "a full bottom row must start the clearing flash"

    theme.color_at(0, 0, STEP * (SandfallTheme._FLASH_STEPS + 2))
    assert _grain_count(theme) == 1, "the bottom row is removed, the grain above survives"
    assert theme._cells[-1][3] is not None, "rows above drop into the cleared space"


def test_idle_board_keeps_moving_on_its_own():
    theme = SandfallTheme()
    frames = [_frame(theme, second * 1.0) for second in range(5)]
    assert all(earlier != later for earlier, later in zip(frames, frames[1:]))


def test_replaying_from_the_start_is_deterministic():
    theme = SandfallTheme()
    first_run = _frame(theme, 6.0)
    _frame(theme, 0.0)  # time went backwards: the world restarts
    assert _frame(theme, 6.0) == first_run


def test_a_long_gap_does_not_replay_every_step():
    theme = _quiet_sandfall()
    theme.color_at(0, 0, 0.0)
    theme.color_at(0, 0, 3600.0)
    assert theme._simulated_until > 3600.0 - SandfallTheme.max_catch_up_seconds - STEP


def test_brightness_wrapper_forwards_key_presses():
    theme = _quiet_sandfall()
    dimmed = BrightnessAdjusted(theme, 0.5)
    dimmed.color_at(0, 0, 0.0)
    dimmed.on_key_press(Q_ROW, Q_COLUMN)
    dimmed.color_at(0, 0, STEP)
    assert _grain_count(theme) == 1


def test_the_spacebar_shows_all_the_sand_beneath_it():
    from f87pro.simulation import _key_pixels
    assert _key_pixels(5, 3) == (4, 5, 6, 7, 8, 9)
