"""
Physical layout of the Aula F87 Pro (TKL, 102 addressable LEDs).

Kept separate from the device layer so themes and the terminal preview can
reason about key geometry without importing a HID backend.
"""
from typing import Dict, List, Tuple

LED_COUNT = 102

#: LED index -> (row, column) on the physical board.
KEY_POSITIONS: Dict[int, Tuple[int, int]] = {
    # Function row
    0: (0, 0), 12: (0, 1), 18: (0, 2), 24: (0, 3), 30: (0, 4), 36: (0, 5),
    42: (0, 6), 48: (0, 7), 54: (0, 8), 60: (0, 9), 66: (0, 10), 72: (0, 11),
    78: (0, 12), 84: (0, 13), 90: (0, 14), 96: (0, 15),

    # Number row
    1: (1, 0), 7: (1, 1), 13: (1, 2), 19: (1, 3), 25: (1, 4), 31: (1, 5),
    37: (1, 6), 43: (1, 7), 49: (1, 8), 55: (1, 9), 61: (1, 10), 67: (1, 11),
    73: (1, 12), 79: (1, 13), 85: (1, 14), 91: (1, 15), 97: (1, 16),

    # Tab row
    2: (2, 0), 8: (2, 1), 14: (2, 2), 20: (2, 3), 26: (2, 4), 32: (2, 5),
    38: (2, 6), 44: (2, 7), 50: (2, 8), 56: (2, 9), 62: (2, 10), 68: (2, 11),
    74: (2, 12), 80: (2, 13), 86: (2, 14), 92: (2, 15), 98: (2, 16),

    # Caps row
    3: (3, 0), 9: (3, 1), 15: (3, 2), 21: (3, 3), 27: (3, 4), 33: (3, 5),
    39: (3, 6), 45: (3, 7), 51: (3, 8), 57: (3, 9), 63: (3, 10), 69: (3, 11),
    81: (3, 12),

    # Shift row
    4: (4, 0), 10: (4, 1), 16: (4, 2), 22: (4, 3), 28: (4, 4), 34: (4, 5),
    40: (4, 6), 46: (4, 7), 52: (4, 8), 58: (4, 9), 64: (4, 10), 82: (4, 11),
    94: (4, 12),

    # Bottom row
    5: (5, 0), 11: (5, 1), 17: (5, 2), 35: (5, 3), 53: (5, 4), 59: (5, 5),
    65: (5, 6), 83: (5, 7), 89: (5, 8), 95: (5, 9), 101: (5, 10),
}

#: Width of the board in 1u key widths (15u main block + gap + 3u nav cluster).
BOARD_WIDTH_UNITS = 18.25

# Horizontal centre of every key, in 1u key widths from the board's left edge,
# listed per row in column order. Column indices are only a packing order: the
# stagger, the wide modifiers and the spacebar mean column 8 sits at a very
# different place on each row. Themes that draw real shapes (circles, letters)
# need the true position or the shape shears apart.
_KEY_CENTERS_BY_ROW = (
    # Esc, F1-F4, F5-F8, F9-F12, PrtSc/ScrLk/Pause
    (0.5, 2.5, 3.5, 4.5, 5.5, 7.0, 8.0, 9.0, 10.0, 11.5, 12.5, 13.5, 14.5,
     15.75, 16.75, 17.75),
    # ` 1-0 - =, Backspace (2u), Ins/Home/PgUp
    (0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5,
     14.0, 15.75, 16.75, 17.75),
    # Tab (1.5u), Q-], Backslash (1.5u), Del/End/PgDn
    (0.75, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0,
     14.25, 15.75, 16.75, 17.75),
    # Caps (1.75u), A-', Enter (2.25u)
    (0.875, 2.25, 3.25, 4.25, 5.25, 6.25, 7.25, 8.25, 9.25, 10.25, 11.25,
     12.25, 13.875),
    # Shift (2.25u), Z-/, Shift (2.75u), Up
    (1.125, 2.75, 3.75, 4.75, 5.75, 6.75, 7.75, 8.75, 9.75, 10.75, 11.75,
     13.625, 16.75),
    # Ctrl/Win/Alt (1.25u), Space (6.25u), Alt/Fn/Menu/Ctrl (1.25u), arrows
    (0.625, 1.875, 3.125, 6.875, 10.625, 11.875, 13.125, 14.375,
     15.75, 16.75, 17.75),
)


def physical_x(row: int, column: int) -> float:
    """
    Horizontal centre of a key on the physical board.

    @param row - Physical row index.
    @param column - Column index within that row.
    @returns The centre in 1u key widths from the left edge. Positions with no
        key fall back to the column index, so callers can sweep the full grid.
    """
    if 0 <= row < len(_KEY_CENTERS_BY_ROW):
        centers = _KEY_CENTERS_BY_ROW[row]
        if 0 <= column < len(centers):
            return centers[column]
    return float(column)


#: Columns of the square pixel grid laid over the board for drawing text.
PIXEL_COLUMNS = 18

# A pixel further than this from every key centre sits over a physical gap
# (such as between Esc and F1) and is simply not shown.
_MAX_PIXEL_DISTANCE = 0.9


def _assign_pixels_to_keys() -> Dict[Tuple[int, int], Tuple[int, ...]]:
    """
    Give each 1u pixel column of each row to the key nearest to it.

    Keys do not sit on a grid: rows are staggered by quarter keys and modifiers
    are wide. Nearest-key ownership keeps glyph strokes vertical (2/Q/A/Z share
    a column) and lets a wide key stand in for every pixel it covers, so no
    part of a letter vanishes under Tab, Shift or Backspace.
    """
    owned: Dict[Tuple[int, int], List[int]] = {}
    for row, centers in enumerate(_KEY_CENTERS_BY_ROW):
        for pixel in range(PIXEL_COLUMNS):
            pixel_center = pixel + 0.5
            column = min(range(len(centers)),
                         key=lambda index: abs(centers[index] - pixel_center))
            if abs(centers[column] - pixel_center) <= _MAX_PIXEL_DISTANCE:
                owned.setdefault((row, column), []).append(pixel)
    return {key: tuple(pixels) for key, pixels in owned.items()}


_PIXELS_BY_KEY = _assign_pixels_to_keys()


def pixel_columns(row: int, column: int) -> Tuple[int, ...]:
    """
    Pixel columns of the text grid that a key displays.

    @param row - Physical row index.
    @param column - Column index within that row.
    @returns The owned pixel columns; empty for positions with no key or keys
        squeezed out by closer neighbours.
    """
    return _PIXELS_BY_KEY.get((row, column), ())


#: Short labels per LED, used only by the terminal preview.
KEY_LABELS: Dict[int, str] = {
    0: "Esc", 12: "F1", 18: "F2", 24: "F3", 30: "F4", 36: "F5", 42: "F6",
    48: "F7", 54: "F8", 60: "F9", 66: "F10", 72: "F11", 78: "F12",
    84: "PrS", 90: "Scr", 96: "Pau",

    1: "`", 7: "1", 13: "2", 19: "3", 25: "4", 31: "5", 37: "6", 43: "7",
    49: "8", 55: "9", 61: "0", 67: "-", 73: "=", 79: "Bks", 85: "Ins",
    91: "Hom", 97: "PgU",

    2: "Tab", 8: "Q", 14: "W", 20: "E", 26: "R", 32: "T", 38: "Y", 44: "U",
    50: "I", 56: "O", 62: "P", 68: "[", 74: "]", 80: "\\", 86: "Del",
    92: "End", 98: "PgD",

    3: "Cap", 9: "A", 15: "S", 21: "D", 27: "F", 33: "G", 39: "H", 45: "J",
    51: "K", 57: "L", 63: ";", 69: "'", 81: "Ent",

    4: "Sft", 10: "Z", 16: "X", 22: "C", 28: "V", 34: "B", 40: "N", 46: "M",
    52: ",", 58: ".", 64: "/", 82: "Sft", 94: "Up",

    5: "Ctl", 11: "Win", 17: "Alt", 35: "Space", 53: "Alt", 59: "Fn",
    65: "Mnu", 83: "Ctl", 89: "Lft", 95: "Dwn", 101: "Rgt",
}

#: LEDs grouped into physical rows, left to right.
ROWS = [
    [led for led, (row, _) in sorted(KEY_POSITIONS.items(), key=lambda item: item[1])
     if row == target_row]
    for target_row in range(6)
]
