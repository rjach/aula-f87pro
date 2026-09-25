"""
macOS virtual keycode -> LED index mapping for the F87 Pro.

Quartz reports hardware-independent virtual keycodes (the `kVK_*` constants),
which are stable across keyboard layouts because they describe key *position*,
not the character produced. That is exactly what a positional lighting effect
needs.
"""
from typing import Dict, Optional

#: kVK_* virtual keycode -> LED index on the board.
MACOS_KEYCODE_TO_LED: Dict[int, int] = {
    # Letters
    0: 9,    # A
    1: 15,   # S
    2: 21,   # D
    3: 27,   # F
    4: 39,   # H
    5: 33,   # G
    6: 10,   # Z
    7: 16,   # X
    8: 22,   # C
    9: 28,   # V
    11: 34,  # B
    12: 8,   # Q
    13: 14,  # W
    14: 20,  # E
    15: 26,  # R
    16: 38,  # Y
    17: 32,  # T
    31: 56,  # O
    32: 44,  # U
    34: 50,  # I
    35: 62,  # P
    37: 57,  # L
    38: 45,  # J
    40: 51,  # K
    45: 40,  # N
    46: 46,  # M

    # Number row
    18: 7,   # 1
    19: 13,  # 2
    20: 19,  # 3
    21: 25,  # 4
    23: 31,  # 5
    22: 37,  # 6
    26: 43,  # 7
    28: 49,  # 8
    25: 55,  # 9
    29: 61,  # 0
    27: 67,  # -
    24: 73,  # =
    50: 1,   # `

    # Punctuation
    33: 68,  # [
    30: 74,  # ]
    42: 80,  # backslash
    41: 63,  # ;
    39: 69,  # '
    43: 52,  # ,
    47: 58,  # .
    44: 64,  # /

    # Editing / whitespace
    48: 2,   # Tab
    49: 35,  # Space
    36: 81,  # Return
    51: 79,  # Backspace
    53: 0,   # Escape

    # Modifiers
    57: 3,   # Caps Lock
    56: 4,   # Left Shift
    60: 82,  # Right Shift
    59: 5,   # Left Control
    62: 83,  # Right Control
    55: 11,  # Left Command -> Win key position
    58: 17,  # Left Option -> Alt position
    61: 53,  # Right Option
    63: 59,  # Fn

    # Function row
    122: 12,  # F1
    120: 18,  # F2
    99: 24,   # F3
    118: 30,  # F4
    96: 36,   # F5
    97: 42,   # F6
    98: 48,   # F7
    100: 54,  # F8
    101: 60,  # F9
    109: 66,  # F10
    103: 72,  # F11
    111: 78,  # F12
    105: 84,  # F13 -> Print Screen
    107: 90,  # F14 -> Scroll Lock
    113: 96,  # F15 -> Pause

    # Navigation cluster
    114: 85,  # Help/Insert
    115: 91,  # Home
    116: 97,  # Page Up
    117: 86,  # Forward Delete
    119: 92,  # End
    121: 98,  # Page Down

    # Arrows
    126: 94,  # Up
    123: 89,  # Left
    125: 95,  # Down
    124: 101,  # Right
}


def led_for_keycode(keycode: int) -> Optional[int]:
    """
    Resolve a macOS virtual keycode to an LED index.

    @param keycode - A kVK_* virtual keycode from a Quartz key event.
    @returns The LED index, or None for keys this board does not have.
    """
    return MACOS_KEYCODE_TO_LED.get(keycode)


# ---------------------------------------------------------------------------
# Modifier keys
# ---------------------------------------------------------------------------
#
# Modifiers do not emit key-down events at all -- macOS reports them as
# `flagsChanged` instead. A listener watching only key-down therefore never
# sees Shift, Control, Option, Command, Caps Lock or Fn, which is why those
# keys stayed dark.

CG_FLAG_ALPHA_SHIFT = 0x00010000   # Caps Lock
CG_FLAG_SHIFT = 0x00020000
CG_FLAG_CONTROL = 0x00040000
CG_FLAG_ALTERNATE = 0x00080000     # Option
CG_FLAG_COMMAND = 0x00100000
CG_FLAG_SECONDARY_FN = 0x00800000

#: Virtual keycode -> the modifier flag that key toggles.
MODIFIER_FLAG_BY_KEYCODE: Dict[int, int] = {
    56: CG_FLAG_SHIFT,          # Left Shift
    60: CG_FLAG_SHIFT,          # Right Shift
    59: CG_FLAG_CONTROL,        # Left Control
    62: CG_FLAG_CONTROL,        # Right Control
    58: CG_FLAG_ALTERNATE,      # Left Option
    61: CG_FLAG_ALTERNATE,      # Right Option
    55: CG_FLAG_COMMAND,        # Left Command
    54: CG_FLAG_COMMAND,        # Right Command
    57: CG_FLAG_ALPHA_SHIFT,    # Caps Lock
    63: CG_FLAG_SECONDARY_FN,   # Fn
}

# Right Command sits where this board prints the Menu key, the only key the
# key-down map could not reach.
MACOS_KEYCODE_TO_LED.setdefault(54, 65)


# ---------------------------------------------------------------------------
# Media keys
# ---------------------------------------------------------------------------
#
# When the function row acts as media keys, those presses are not key events
# either: they arrive as system-defined events carrying an NX_KEYTYPE_* code.
# Without handling them, the whole function row stays dark.

NX_KEYTYPE_SOUND_UP = 0
NX_KEYTYPE_SOUND_DOWN = 1
NX_KEYTYPE_BRIGHTNESS_UP = 2
NX_KEYTYPE_BRIGHTNESS_DOWN = 3
NX_KEYTYPE_MUTE = 7
NX_KEYTYPE_PLAY = 16
NX_KEYTYPE_NEXT = 17
NX_KEYTYPE_PREVIOUS = 18
NX_KEYTYPE_FAST = 19
NX_KEYTYPE_REWIND = 20
NX_KEYTYPE_ILLUMINATION_UP = 21
NX_KEYTYPE_ILLUMINATION_DOWN = 22

#: NX_KEYTYPE_* -> LED, following the standard Mac function-row arrangement.
MEDIA_KEY_TO_LED: Dict[int, int] = {
    NX_KEYTYPE_BRIGHTNESS_DOWN: 12,   # F1
    NX_KEYTYPE_BRIGHTNESS_UP: 18,     # F2
    NX_KEYTYPE_ILLUMINATION_DOWN: 36,  # F5
    NX_KEYTYPE_ILLUMINATION_UP: 42,   # F6
    NX_KEYTYPE_PREVIOUS: 48,          # F7
    NX_KEYTYPE_REWIND: 48,            # F7 (held)
    NX_KEYTYPE_PLAY: 54,              # F8
    NX_KEYTYPE_NEXT: 60,              # F9
    NX_KEYTYPE_FAST: 60,              # F9 (held)
    NX_KEYTYPE_MUTE: 66,              # F10
    NX_KEYTYPE_SOUND_DOWN: 72,        # F11
    NX_KEYTYPE_SOUND_UP: 78,          # F12
}

#: Key-state nibble in a system-defined event's data1 meaning "pressed".
NX_KEY_DOWN = 0x0A


def led_for_media_key(media_keycode: int) -> Optional[int]:
    """
    Resolve an NX_KEYTYPE_* media keycode to an LED index.

    @param media_keycode - The NX_KEYTYPE_* code from a system-defined event.
    @returns The LED index, or None if this board has no such key.
    """
    return MEDIA_KEY_TO_LED.get(media_keycode)


def modifier_flag(keycode: int) -> Optional[int]:
    """
    The modifier flag a keycode toggles, if it is a modifier at all.

    @param keycode - A kVK_* virtual keycode.
    @returns The CGEventFlags mask, or None for non-modifier keys.
    """
    return MODIFIER_FLAG_BY_KEYCODE.get(keycode)
