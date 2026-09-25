"""
Keystroke-reactive lighting: a still base layer with 3D bubbles on key press.

The base never animates -- every key holds its own steady colour -- and each
keystroke raises a short-lived bubble centred on the key that was pressed.

The bubble is shaded like a real one rather than drawn as a flat ring:

* a **dome** term, `sqrt(1 - (d/R)^2)`, which is the height profile of a
  hemisphere and makes the interior read as curved rather than flat;
* a bright **rim** at the expanding shell, since a soap bubble is thinnest and
  brightest at its silhouette edge;
* a small off-centre **specular** highlight, the single strongest 3D cue,
  offset up and to the left as though lit from that direction.
"""
import math
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from .layout import KEY_POSITIONS, LED_COUNT
from .themes import RGB

# --- Bubble shape and timing ------------------------------------------------

#: How long one bubble lives, in seconds.
BUBBLE_LIFETIME = 1.15
#: How far a bubble spreads, in key widths.
BUBBLE_MAX_RADIUS = 5.6
#: Thickness of the wave crest. Tight, so it reads as a travelling front
#: rather than a filled disc.
_RIM_SIGMA = 0.45
#: Thickness of the trailing ripple behind the crest.
_RIPPLE_SIGMA = 0.7
#: Where the trailing ripple sits, as a fraction of the crest radius.
_RIPPLE_RADIUS_FRACTION = 0.55
#: Tightness of the specular highlight.
_SPECULAR_SIGMA = 0.75
#: Where the highlight sits relative to the centre (rows, columns): up-left.
_SPECULAR_OFFSET = (-0.55, -0.7)

#: Shape of the expansion. Below 1.0 the wave still eases outward, but travels
#: steadily across its whole life rather than sprinting to near-full size in
#: the first third and then sitting still.
_EXPANSION_EXPONENT = 0.8
#: Shape of the fade. `1 - p**n` holds the wave near full strength through the
#: middle of its life and drops away at the end, unlike `(1 - p)**n` which
#: starts dimming immediately and leaves most of a long bubble invisible.
_FADE_EXPONENT = 2.4

# Relative strengths of the shading terms. The interior fill is almost nothing:
# a wave is a moving front, so the crest and its trailing ripple carry the
# shape and the inside is left open for the base to show through.
_DOME_WEIGHT = 0.06
_RIM_WEIGHT = 1.45
_RIPPLE_WEIGHT = 0.40
_SPECULAR_WEIGHT = 0.95

#: Gamma applied to every light contribution before it is added.
#:
#: Desaturation peaks at *moderate* intensity: a faint light over a saturated
#: base barely shifts it, and a strong one overrides it, but halfway between
#: the two averages toward grey. Raising the amount to a power above 1
#: collapses that middle band, so keys land on one side or the other instead
#: of in the muddy centre.
_LIGHT_GAMMA = 1.75

#: Colours issued to successive bubbles, in order.
#:
#: Consecutive presses must be told apart at a glance, so neighbouring entries
#: are far apart in hue. They are all bright and near-saturated because the
#: base is a dim rainbow: a bubble cannot rely on hue alone to separate from a
#: base that contains every hue, so it separates on brightness as well and
#: stays legible even when it crosses a base region of its own colour.
BUBBLE_COLORS: List[RGB] = [
    (255, 255, 255),   # white
    (255, 176, 48),    # amber
    (90, 230, 255),    # cyan
    (255, 86, 170),    # hot pink
    (168, 255, 110),   # lime
    (170, 140, 255),   # violet
    (255, 120, 66),    # coral
]

#: The specular hotspot stays white whatever colour the bubble is; a highlight
#: is the light source reflected, not the surface's own colour.
_SPECULAR_TINT: RGB = (255, 255, 255)

#: Above this many simultaneous bubbles the oldest are dropped.
MAX_ACTIVE_BUBBLES = 40
#: A key retriggered faster than this just restarts its bubble.
_RETRIGGER_SECONDS = 0.04

#: How quickly the energy from one keystroke drains away, in seconds.
_ENERGY_DECAY_SECONDS = 0.6
#: Recent keystrokes needed to get most of the way to full energy. Roughly a
#: fast typist's sustained rate, so ordinary typing visibly builds the surge.
_ENERGY_SATURATION = 4.0


def _build_distance_table() -> Dict[int, Dict[int, float]]:
    """
    Precompute distances between every pair of mapped keys.

    Rendering touches this on every frame for every bubble, so paying once at
    import time keeps the frame loop free of trigonometry.

    @returns origin LED -> {other LED -> distance in key widths}.
    """
    table: Dict[int, Dict[int, float]] = {}
    for origin, (origin_row, origin_col) in KEY_POSITIONS.items():
        distances: Dict[int, float] = {}
        for target, (target_row, target_col) in KEY_POSITIONS.items():
            row_delta = target_row - origin_row
            col_delta = target_col - origin_col
            distances[target] = math.hypot(row_delta, col_delta)
        table[origin] = distances
    return table


_DISTANCES = _build_distance_table()


def _specular_distance(origin: int, target: int) -> float:
    """Distance from a key to the bubble's offset highlight point."""
    origin_row, origin_col = KEY_POSITIONS[origin]
    target_row, target_col = KEY_POSITIONS[target]
    highlight_row = origin_row + _SPECULAR_OFFSET[0]
    highlight_col = origin_col + _SPECULAR_OFFSET[1]
    return math.hypot(target_row - highlight_row, target_col - highlight_col)


_SPECULAR_DISTANCES = {
    origin: {target: _specular_distance(origin, target) for target in KEY_POSITIONS}
    for origin in KEY_POSITIONS
}


def _add_light(base: RGB, tint: RGB, amount: float) -> RGB:
    """
    Add coloured light to a colour, the way a real light source behaves.

    Interpolating *toward* a tint is wrong here: the base is cool teal-violet
    and the bubble is warm, and lerping between complementary hues passes
    through desaturated olive-brown, which looks like mud on the board. Adding
    light instead keeps both hues intact -- unlit keys stay teal, lit keys go
    warm -- and only blows out to white where the light is genuinely intense.

    @param base - The colour already on the key.
    @param tint - The colour of the light being added.
    @param amount - Intensity of the light, >= 0.
    @returns The lit colour, clamped per channel.
    """
    return (
        min(255, int(base[0] + tint[0] * amount)),
        min(255, int(base[1] + tint[1] * amount)),
        min(255, int(base[2] + tint[2] * amount)),
    )


def _shaped(lift: float) -> float:
    """
    Clamp a light contribution and apply the contrast gamma.

    @param lift - Raw, unclamped shading amount.
    @returns The amount to actually add, in the 0.0-1.0 range.
    """
    return min(1.0, max(0.0, lift)) ** _LIGHT_GAMMA


class BubbleField:
    """
    Tracks live bubbles and composites them over a still base layer.

    Key presses arrive on a listener thread while frames are rendered on the
    main thread, so the active-bubble list is guarded by a lock.
    """

    def __init__(self, lifetime: float = BUBBLE_LIFETIME,
                 max_radius: float = BUBBLE_MAX_RADIUS,
                 colors: Optional[List[RGB]] = None):
        """
        @param lifetime - Seconds a wave takes to travel out and fade.
        @param max_radius - Final crest radius in key widths.
        @param colors - Colours issued to successive bubbles, cycled in order.
        """
        self._lifetime = lifetime
        self._max_radius = max_radius
        self._colors = list(colors) if colors else list(BUBBLE_COLORS)
        self._next_color = 0
        self._bubbles: Deque[Tuple[int, float, RGB]] = deque(maxlen=MAX_ACTIVE_BUBBLES)
        self._lock = threading.Lock()

    def trigger(self, led: int, when: Optional[float] = None) -> None:
        """
        Start a wave at a key, in the next colour of the cycle.

        @param led - LED index of the pressed key.
        @param when - Start timestamp; defaults to now.
        """
        if led not in KEY_POSITIONS:
            return

        start = time.time() if when is None else when
        with self._lock:
            # Held keys repeat quickly; restart rather than stacking near-identical
            # waves, which would just look like a flicker. Reuse the colour so a
            # repeat does not consume the next one in the cycle.
            for index, (existing_led, existing_start, existing_color) in enumerate(self._bubbles):
                if existing_led == led and start - existing_start < _RETRIGGER_SECONDS:
                    self._bubbles[index] = (led, start, existing_color)
                    return

            color = self._colors[self._next_color % len(self._colors)]
            self._next_color += 1
            self._bubbles.append((led, start, color))

    def energy(self, now: Optional[float] = None) -> float:
        """
        How hard the board is being typed on right now.

        Each keystroke adds a unit of energy that decays exponentially, so a
        burst of typing builds up and a pause lets it drain rather than the
        value snapping between on and off.

        @param now - Timestamp to measure at; defaults to now.
        @returns Energy in the 0.0-1.0 range, approaching 1.0 under fast typing.
        """
        timestamp = time.time() if now is None else now
        with self._lock:
            ages = [timestamp - start for _, start, _ in self._bubbles]
        raw = sum(math.exp(-age / _ENERGY_DECAY_SECONDS) for age in ages if age >= 0.0)
        return 1.0 - math.exp(-raw / _ENERGY_SATURATION * 2.0)

    def _active(self, now: float) -> List[Tuple[int, float, RGB]]:
        """Return live waves as (led, progress, colour), dropping expired ones."""
        with self._lock:
            live = []
            for led, start, color in self._bubbles:
                progress = (now - start) / self._lifetime
                if 0.0 <= progress < 1.0:
                    live.append((led, progress, color))

            # Prune only waves that have finished. One whose start time is
            # fractionally ahead of this frame's timestamp -- which happens
            # whenever the listener thread fires between frames -- is still
            # pending, not expired, and must survive to be drawn next frame.
            if any((now - start) / self._lifetime >= 1.0 for _, start, _ in self._bubbles):
                self._bubbles = deque(
                    ((led, start, color) for led, start, color in self._bubbles
                     if (now - start) / self._lifetime < 1.0),
                    maxlen=MAX_ACTIVE_BUBBLES,
                )
            return live

    def _lift_at(self, led: int, origin: int,
                 progress: float) -> Tuple[float, float]:
        """
        Shading contribution of one wave at one key.

        @returns (body lift, specular lift), unclamped and >= 0. The body is
                 drawn in the wave's own colour; the specular stays white.
        """
        radius = self._max_radius * (progress ** _EXPANSION_EXPONENT)
        if radius <= 0.0:
            return 0.0, 0.0

        distance = _DISTANCES[origin][led]
        fade = 1.0 - progress ** _FADE_EXPONENT

        # Faint interior fill, just enough to suggest a curved surface.
        if distance < radius:
            normalized = distance / radius
            dome = math.sqrt(max(0.0, 1.0 - normalized * normalized))
        else:
            dome = 0.0

        # The crest: a bright front at the wave's leading edge.
        crest_offset = distance - radius
        crest = math.exp(-(crest_offset * crest_offset) / (2 * _RIM_SIGMA * _RIM_SIGMA))

        # A weaker ripple trailing behind the crest, which is what makes the
        # effect read as a wave travelling outward rather than a single ring.
        ripple_offset = distance - radius * _RIPPLE_RADIUS_FRACTION
        ripple = math.exp(
            -(ripple_offset * ripple_offset) / (2 * _RIPPLE_SIGMA * _RIPPLE_SIGMA)
        )

        # Off-centre highlight, strongest early while the wave is still tight.
        specular_distance = _SPECULAR_DISTANCES[origin][led]
        specular = math.exp(
            -(specular_distance * specular_distance) / (2 * _SPECULAR_SIGMA * _SPECULAR_SIGMA)
        )
        specular *= max(0.0, 1.0 - progress * 1.3)

        body = fade * (
            _DOME_WEIGHT * dome
            + _RIM_WEIGHT * crest
            + _RIPPLE_WEIGHT * ripple
        )
        return body, fade * _SPECULAR_WEIGHT * specular

    def render(self, base_frame: List[int], now: Optional[float] = None) -> List[int]:
        """
        Composite active waves over the base layer.

        @param base_frame - Flat [r, g, b, ...] buffer for the unlit board.
        @param now - Timestamp to render at; defaults to now.
        @returns A new flat buffer with the waves applied.
        """
        timestamp = time.time() if now is None else now
        active = self._active(timestamp)
        if not active:
            return base_frame

        frame = list(base_frame)
        for led in KEY_POSITIONS:
            offset = led * 3
            color: RGB = (frame[offset], frame[offset + 1], frame[offset + 2])
            touched = False

            # The strongest wave at this key wins it outright, rather than every
            # overlapping wave adding its light.
            #
            # Summing is what real lights do, but it defeats the point here:
            # once two or three waves overlap, their colours add toward white
            # and every wave looks the same. Letting the nearest crest own the
            # key keeps each wave its own colour and draws a clean seam where
            # two of them meet.
            strongest_body = 0.0
            strongest_tint: Optional[RGB] = None
            strongest_specular = 0.0

            for origin, progress, tint in active:
                body, specular = self._lift_at(led, origin, progress)
                if body > strongest_body:
                    strongest_body = body
                    strongest_tint = tint
                if specular > strongest_specular:
                    strongest_specular = specular

            if strongest_tint is not None and strongest_body > 0.0:
                color = _add_light(color, strongest_tint, _shaped(strongest_body))
                touched = True
            if strongest_specular > 0.0:
                color = _add_light(color, _SPECULAR_TINT, _shaped(strongest_specular))
                touched = True

            if not touched:
                continue

            frame[offset] = max(0, min(255, color[0]))
            frame[offset + 1] = max(0, min(255, color[1]))
            frame[offset + 2] = max(0, min(255, color[2]))

        return frame


class MacOSKeyListener:
    """
    Watches key presses system-wide via a Quartz event tap.

    The tap is listen-only: it observes key-down events to place bubbles and
    never modifies, blocks or records them. Only the key's position is used --
    no key identity is stored or written anywhere.

    Requires the Input Monitoring permission on the controlling application.
    """

    def __init__(self, on_key_led):
        """
        @param on_key_led - Callback invoked with an LED index per key press.
        """
        self._on_key_led = on_key_led
        self._thread: Optional[threading.Thread] = None
        self._tap = None
        self._stopping = threading.Event()
        self.started = threading.Event()
        self.failure: Optional[str] = None

    def start(self) -> bool:
        """
        Begin listening on a background thread.

        @returns True once the tap is installed, False if it could not be created.
        """
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.started.wait(timeout=5.0)
        return self.failure is None

    def _run(self) -> None:
        try:
            import Quartz
            from CoreFoundation import (CFRunLoopAddSource, CFRunLoopGetCurrent)
            from AppKit import NSEvent
        except ImportError as error:
            self.failure = (
                f"pyobjc is required for keystroke reactivity ({error}). "
                "Install it with: pip install pyobjc-framework-Quartz"
            )
            self.started.set()
            return

        from .keycodes import (NX_KEY_DOWN, led_for_keycode, led_for_media_key,
                               modifier_flag)

        # Not exported by pyobjc under this name, but this is NSSystemDefined.
        system_defined_type = 14

        # Which modifier keys are currently held, so a release does not raise a
        # second bubble.
        modifiers_held = set()

        def handle_key_down(event):
            keycode = Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode
            )
            return led_for_keycode(int(keycode))

        def handle_flags_changed(event):
            """Modifiers report as flag changes, never as key-down events."""
            keycode = int(Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode
            ))
            mask = modifier_flag(keycode)
            if mask is None:
                return None

            is_down = bool(Quartz.CGEventGetFlags(event) & mask)

            # Caps Lock reports its state, not its press: the flag clears when
            # it is switched off, yet that is still a physical press worth a
            # bubble.
            from .keycodes import CG_FLAG_ALPHA_SHIFT
            if mask == CG_FLAG_ALPHA_SHIFT:
                return led_for_keycode(keycode)

            if is_down:
                if keycode in modifiers_held:
                    return None
                modifiers_held.add(keycode)
                return led_for_keycode(keycode)

            # Flag cleared: every key sharing this modifier is now up.
            for held in [k for k in modifiers_held if modifier_flag(k) == mask]:
                modifiers_held.discard(held)
            return None

        def handle_system_defined(event):
            """Media keys arrive as system-defined events, not key events."""
            ns_event = NSEvent.eventWithCGEvent_(event)
            if ns_event is None or ns_event.subtype() != 8:
                return None

            data = ns_event.data1()
            media_keycode = (data & 0xFFFF0000) >> 16
            key_state = (data & 0xFF00) >> 8
            if key_state != NX_KEY_DOWN:
                return None
            return led_for_media_key(int(media_keycode))

        handlers = {
            Quartz.kCGEventKeyDown: handle_key_down,
            Quartz.kCGEventFlagsChanged: handle_flags_changed,
            system_defined_type: handle_system_defined,
        }

        def callback(proxy, event_type, event, refcon):
            handler = handlers.get(event_type)
            if handler is not None:
                try:
                    led = handler(event)
                except Exception:
                    led = None
                if led is not None:
                    self._on_key_led(led)
            return event

        event_mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
            | Quartz.CGEventMaskBit(system_defined_type)
        )

        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            event_mask,
            callback,
            None,
        )

        if not self._tap:
            self.failure = (
                "Could not create a keyboard event tap. Grant Input Monitoring "
                "to your terminal in System Settings -> Privacy & Security, "
                "then reopen it."
            )
            self.started.set()
            return

        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopDefaultMode)
        Quartz.CGEventTapEnable(self._tap, True)
        self.started.set()

        # Wake periodically so stop() is honoured promptly.
        while not self._stopping.is_set():
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.25, False)

    def stop(self) -> None:
        """Stop listening."""
        self._stopping.set()
