import argparse
import sys
import os
import time
import threading
from .device import AulaF87Pro
from .colors import parse_color_input, predefined_colors
from .pywal import load_wal_colors, WalFileWatcher
from .themes import THEMES, DEFAULT_THEME, BrightnessAdjusted, get_theme
from .reactive import BUBBLE_LIFETIME, BUBBLE_MAX_RADIUS, BubbleField, MacOSKeyListener
from .preview import preview as preview_theme
from .layout import KEY_POSITIONS

#: --duration is shared by several effects, but themes should run until
#: interrupted while the older colour effects keep their historic 10s default.
DEFAULT_EFFECT_DURATION = 10.0
DEFAULT_THEME_DURATION = 0.0
FULL_BRIGHTNESS_PERCENT = 100
#: A --preview with no explicit duration runs long enough to judge the theme.
PREVIEW_DURATION = 8.0
#: Bubbles are short and fast, so they need a higher frame rate than a drifting
#: background theme does.
REACTIVE_FPS = 60
#: The moving base is dimmed hard so the warm bubbles read clearly against it.
#: At full brightness the cool gradient competes with the highlight.
REACTIVE_BASE_BRIGHTNESS = 0.40

def create_parser():
    parser = argparse.ArgumentParser(
        description="Control the Aula F87 Pro RGB keyboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aula-f87pro --color red
  aula-f87pro --color "#FF0000"
  aula-f87pro --color "255,0,0"
  aula-f87pro --breathing blue --duration 30
  aula-f87pro --theme aurora       # animated aurora theme (runs until Ctrl+C)
  aula-f87pro --theme dusk --brightness 60
  aula-f87pro --theme aurora --reactive  # flowing base + bubble on each keystroke
  aula-f87pro --theme sandfall --reactive  # every keystroke drops a grain of sand
  aula-f87pro --theme tide --preview   # preview in the terminal, no hardware
  aula-f87pro --list-themes
  aula-f87pro --pywal              # accent color from pywal
  aula-f87pro --pywal gradient     # gradient with pywal colors
  aula-f87pro --test
  aula-f87pro --off
  aula-f87pro --find-interface
        """
    )

     # Device connection options
    parser.add_argument('--find-interface', action='store_true',
                        help='Find and save the working RGB interface')
    parser.add_argument('--force-find', action='store_true',
                        help='Force re-detection of interface (ignore saved)')
    parser.add_argument('--show-config', action='store_true',
                        help='Show current saved configuration')
    
    # Color commands
    parser.add_argument('--color', type=str,
                        help='Set solid color (hex: #FF0000, RGB: 255,0,0, or name: red)')
    parser.add_argument('--breathing', nargs='?', const='__pywal__', default=None,
                        help='Breathing effect with color (same formats as --color). Color optional if --pywal is used.')
    parser.add_argument('--duration', type=float, default=None,
                        help='Effect duration in seconds; 0 runs until Ctrl+C '
                             '(default: 10 for --color/--breathing, 0 for --theme)')

    # Animated themes
    parser.add_argument('--theme', nargs='?', const=DEFAULT_THEME, default=None,
                        choices=sorted(THEMES),
                        help=f'Play an animated per-key theme (default: {DEFAULT_THEME})')
    parser.add_argument('--reactive', action='store_true',
                        help='Dim the theme into a moving backdrop and raise a 3D '
                             'bubble wherever a key is pressed (macOS)')
    parser.add_argument('--list-themes', action='store_true',
                        help='List available themes')
    parser.add_argument('--preview', action='store_true',
                        help='Render the theme in the terminal instead of on the keyboard')
    parser.add_argument('--brightness', type=int, default=FULL_BRIGHTNESS_PERCENT,
                        metavar='1-100',
                        help='Theme brightness percentage (default: 100)')
    
    # Pywal integration
    parser.add_argument('--pywal', nargs='?', const='solid', default=None,
                        choices=['solid', 'gradient'],
                        help='Use pywal colors (solid=accent, gradient=row colors)')
    parser.add_argument('--watch', action='store_true',
                        help='Watch for changes in pywal colors and update automatically')

    # Utility commands
    parser.add_argument('--test', action='store_true',
                        help='Run RGB test sequence')
    parser.add_argument('--off', action='store_true',
                        help='Turn off all lighting')
    parser.add_argument('--list-colors', action='store_true',
                        help='List available predefined colors')
    
    return parser

def _resolve_duration(args, fallback: float) -> float:
    """
    Pick the effect duration, honouring an explicit --duration.

    @param args - Parsed CLI arguments.
    @param fallback - Duration to use when --duration was not passed.
    @returns The duration in seconds.
    """
    return fallback if args.duration is None else args.duration


def _build_theme(theme_name: str, brightness_percent: int):
    """
    Resolve a theme by name and apply the requested brightness.

    @param theme_name - Name of a registered theme.
    @param brightness_percent - Brightness from 1 to 100.
    @returns The theme, wrapped for brightness when it is not already full.
    @raises ValueError If the brightness is outside the valid range.
    """
    if not 1 <= brightness_percent <= FULL_BRIGHTNESS_PERCENT:
        raise ValueError(
            f"Brightness must be between 1 and {FULL_BRIGHTNESS_PERCENT}, "
            f"got {brightness_percent}"
        )

    theme = get_theme(theme_name)
    if brightness_percent == FULL_BRIGHTNESS_PERCENT:
        return theme
    return BrightnessAdjusted(theme, brightness_percent / FULL_BRIGHTNESS_PERCENT)


def main():
    parser = create_parser()
    args = parser.parse_args()
    keyboard = AulaF87Pro()
    
    if args.list_colors:
        print("Available predefined colors:")
        colors = predefined_colors()
        for name, rgb in colors.items():
            print(f"  {name:<10} RGB{rgb}")
        return 0
    
    
    if args.list_themes:
        print("Available themes:")
        for theme_name in sorted(THEMES):
            print(f"  {theme_name:<10} {THEMES[theme_name].description}")
        print(f"\nDefault: {DEFAULT_THEME}")
        print("Preview one without hardware:  aula-f87pro --theme aurora --preview")
        return 0

    if args.show_config:
        keyboard.config_manager.show_config()
        return 0
    
    if args.find_interface:
        path = keyboard.find_working_interface()
        if path:
            print(f"\nWorking interface found and saved!")
            print("You can now use other commands.")
        else:
            print("No working interface found.")
            return 1
        return 0
    
    if args.theme:
        try:
            selected_theme = _build_theme(args.theme, args.brightness)
        except ValueError as error:
            print(f"Error: {error}")
            return 1

        if args.preview:
            preview_theme(
                selected_theme,
                duration=_resolve_duration(args, DEFAULT_THEME_DURATION) or PREVIEW_DURATION,
            )
            return 0

    if not keyboard.connect(force_find=args.force_find):
        print("\nFailed to connect to keyboard.")
        print("Once access is granted, try --find-interface to confirm the RGB interface.")
        if args.theme:
            print(f"Meanwhile you can preview the theme: "
                  f"aula-f87pro --theme {args.theme} --preview")
        return 1
    
    try:
        if args.off:
            print("Turning off all lighting...")
            if keyboard.turn_off():
                print("Lighting turned off.")
            else:
                print("Failed to turn off lighting.")
                return 1
        
        elif args.test:
            keyboard.test_sequence()
            print("Test sequence completed.")
        
        elif args.color:
            try:
                r, g, b = parse_color_input(args.color)
                print(f"Setting solid color: RGB({r}, {g}, {b})")
                if keyboard.set_solid_color(r, g, b, _resolve_duration(args, DEFAULT_EFFECT_DURATION)):
                    print("Color set successfully.")
                else:
                    print("Failed to set color.")
                    return 1
            except ValueError as e:
                print(f"Error parsing color: {e}")
                return 1
        
        elif args.theme and args.reactive:
            base_brightness = selected_theme.reactive_base_brightness
            if base_brightness is None:
                base_brightness = REACTIVE_BASE_BRIGHTNESS
            base = BrightnessAdjusted(selected_theme, base_brightness)
            field = BubbleField(
                lifetime=selected_theme.reactive_bubble_lifetime or BUBBLE_LIFETIME,
                max_radius=selected_theme.reactive_bubble_radius or BUBBLE_MAX_RADIUS,
            )
            def on_key_led(led):
                field.trigger(led)
                position = KEY_POSITIONS.get(led)
                if position is not None:
                    selected_theme.on_key_press(*position)

            listener = MacOSKeyListener(on_key_led=on_key_led)

            if not listener.start():
                print(f"Error: {listener.failure}")
                return 1

            print("Listening for keystrokes (key positions only; nothing is recorded).")
            try:
                if not keyboard.run_reactive(
                    base, field,
                    duration=_resolve_duration(args, DEFAULT_THEME_DURATION),
                    frames_per_second=REACTIVE_FPS,
                ):
                    return 1
            finally:
                listener.stop()

        elif args.theme:
            if not keyboard.run_theme(
                selected_theme, _resolve_duration(args, DEFAULT_THEME_DURATION)
            ):
                return 1

        elif args.breathing or args.pywal:
            # State for watch mode - uses threading.Event for signaling
            change_event = threading.Event()
            stop_flag = threading.Event()
            
            # Callback for the file watcher
            def on_colors_changed():
                print("Pywal colors changed. Reloading...")
                change_event.set()
            
            # Start watcher if in watch mode
            watcher = None
            if args.watch:
                watcher = WalFileWatcher(on_change=on_colors_changed, debounce_seconds=1.0)
                watcher.start()
                print("Watching for pywal changes using inotify...")
            
            # Callback for effects to check if they should stop
            def should_stop_check():
                return change_event.is_set() or stop_flag.is_set()

            try:
                while True:
                    change_event.clear()
                    
                    # Load colors if potentially needed
                    colors = None
                    if args.pywal or (args.breathing == '__pywal__'):
                        colors = load_wal_colors()
                        if not colors and args.watch:
                            # If file disappears or is empty, wait and retry
                            time.sleep(1)
                            continue
                        elif not colors:
                            print("Error: Could not load pywal colors.")
                            return 1

                    # --- Breathing Logic ---
                    if args.breathing:
                        r, g, b = 0, 0, 0
                        base_data = None
                        if args.breathing == '__pywal__':
                            if args.pywal == 'gradient':
                                base_data = keyboard.create_gradient_data(colors)
                            else:
                                if len(colors) > 1: r, g, b = colors[1]
                                elif len(colors) > 0: r, g, b = colors[0]
                        else:
                            try:
                                r, g, b = parse_color_input(args.breathing)
                            except: pass 

                        if base_data:
                            print(f"Starting {'watched ' if args.watch else ''}breathing effect (Gradient)...")
                            keyboard.breathing_effect(0, 0, 0, _resolve_duration(args, DEFAULT_EFFECT_DURATION) if not args.watch else 0, base_rgb_data=base_data, should_stop=should_stop_check)
                        else:
                            print(f"Starting {'watched ' if args.watch else ''}breathing effect RGB({r},{g},{b})...")
                            keyboard.breathing_effect(r, g, b, _resolve_duration(args, DEFAULT_EFFECT_DURATION) if not args.watch else 0, should_stop=should_stop_check)

                    # --- Static Pywal Logic (if not breathing) ---
                    elif args.pywal:
                        if args.pywal == 'gradient':
                            print(f"Starting {'watched ' if args.watch else ''}pywal gradient...")
                            keyboard.set_pywal_gradient(colors, _resolve_duration(args, DEFAULT_EFFECT_DURATION) if not args.watch else 0, should_stop=should_stop_check)
                        else:
                            # Solid accent
                            if len(colors) > 1: r, g, b = colors[1]
                            elif len(colors) > 0: r, g, b = colors[0]
                            else: r,g,b = 255,255,255
                            
                            print(f"Starting {'watched ' if args.watch else ''}pywal solid RGB({r},{g},{b})...")
                            keyboard.set_solid_color(r, g, b, _resolve_duration(args, DEFAULT_EFFECT_DURATION) if not args.watch else 0, should_stop=should_stop_check)
                    
                    # If not watching, or we stopped for a reason other than file change, exit
                    if not args.watch or not change_event.is_set():
                        break
                    
            finally:
                if watcher:
                    watcher.stop()

        else:
            print("No command specified. Use --help for available options.")
            return 1
    
    except KeyboardInterrupt:
        print("\nOperation interrupted.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
    finally:
        keyboard.disconnect()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())