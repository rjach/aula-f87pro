import time
import os
from typing import Optional, Callable
from .config import ConfigManager
from .hid_backend import hid, permission_hint, sharing_warning
from .layout import KEY_POSITIONS as LAYOUT_KEY_POSITIONS, LED_COUNT
from .themes import Theme, is_static

class AulaF87Pro:
    #: The board holds no state, so an idle picture must be refreshed.
    KEEPALIVE_SECONDS = 1.0

    VENDOR_ID = 0x258a
    PRODUCT_ID = 0x010c

    # LED indices for each key - organized by physical layout
    KEY_INDICES = [
        0,   12,18,24,30,36,42,48,54,60,66,72,78,84,90,96,   
        1, 7,13,19,25,31,37,43,49,55,61,67,73,79,85,91,97,
        2, 8,14,20,26,32,38,44,50,56,62,68,74,80,86,92,98,
        3, 9,15,21,27,33,39,45,51,57,63,69,   81,  
        4,10,16,22,28,34,40,46,52,58,64,      82,   94,
        5,11,17,      35,      53,59,65,      83,89,95,101
    ]
    
    # Physical key positions (row, col), sourced from the shared layout module.
    KEY_POSITIONS = LAYOUT_KEY_POSITIONS

    KEY_MAP = {
        # Letters
        'a': 9, 'b': 46, 'c': 34, 'd': 21, 'e': 20, 'f': 27, 'g': 33, 'h': 39,
        'i': 56, 'j': 45, 'k': 51, 'l': 57, 'm': 52, 'n': 40, 'o': 62, 'p': 68,
        'q': 8, 'r': 26, 's': 15, 't': 32, 'u': 50, 'v': 28, 'w': 14, 'x': 22,
        'y': 44, 'z': 16,
        
        # Numbers
        '1': 7, '2': 13, '3': 19, '4': 25, '5': 31, '6': 37, '7': 43, '8': 49,
        '9': 55, '0': 61,
        
        # Function keys
        'f1': 12, 'f2': 18, 'f3': 24, 'f4': 30, 'f5': 36, 'f6': 42, 'f7': 48,
        'f8': 54, 'f9': 60, 'f10': 66, 'f11': 72, 'f12': 78,
        
        'space': 35, 'enter': 81, 'shift': 4, 'ctrl': 5, 'alt': 11, # 'shift_l', 'ctrl_l', 'alt_l' might be more specific
        'tab': 2, 'caps_lock': 3, 'backspace': 85, 'escape': 0,
        
        # Punctuation
        ';': 63, "'": 69, ',': 58, '.': 64, '/': 82, '\\': 92, '[': 74, ']': 80,
        '=': 67, '-': 73, '`': 1
    }
    
    def __init__(self):
        self.device = None
        self.device_path = None
        self.num_leds = LED_COUNT
        self.config_manager = ConfigManager(os.path.expanduser("~/.aula_f87_config.json"))
    
    def auto_find_interface(self) -> Optional[str]:
        """Automatically find RGB interface without user interaction."""
        devices = hid.enumerate(self.VENDOR_ID, self.PRODUCT_ID)
        if not devices:
            return None

        # Prefer interface with usage_page 0xff00 (vendor-specific, usually RGB)
        for dev_info in devices:
            if dev_info.get('usage_page') == 0xff00:
                try:
                    temp_device = hid.device()
                    temp_device.open_path(dev_info['path'])
                    # Test with a simple packet. Opening is not proof of
                    # anything: the wrong interface opens happily and then
                    # rejects the report with -1.
                    packet = [0x06, 0x08, 0x00, 0x00, 0x01, 0x00, 0x7a, 0x01]
                    packet.extend([0] * (520 - len(packet)))
                    written = temp_device.send_feature_report(packet)
                    temp_device.close()
                    if not written or written <= 0:
                        continue

                    path = dev_info['path'].decode('utf-8') if isinstance(dev_info['path'], bytes) else dev_info['path']
                    self.config_manager.set('device_path', path)
                    self.config_manager.set('vendor_id', self.VENDOR_ID)
                    self.config_manager.set('product_id', self.PRODUCT_ID)
                    return path
                except:
                    continue

        # Fallback: try interface 1
        for dev_info in devices:
            if dev_info.get('interface_number') == 1:
                try:
                    temp_device = hid.device()
                    temp_device.open_path(dev_info['path'])
                    temp_device.close()
                    path = dev_info['path'].decode('utf-8') if isinstance(dev_info['path'], bytes) else dev_info['path']
                    self.config_manager.set('device_path', path)
                    return path
                except:
                    continue

        return None

    def find_working_interface(self) -> Optional[str]:
        print("Searching for working RGB interface...")

        devices = hid.enumerate(self.VENDOR_ID, self.PRODUCT_ID)
        if not devices:
            print("No Aula F87 Pro devices found.")
            return None

        for i, dev_info in enumerate(devices):
            if i == 0:  # Typically keyboard input interface
                print(f"Skipping interface {i} (likely keyboard input).")
                continue

            print(f"\nTesting interface {i}...")
            print(f"  Path: {dev_info['path']}")
            print(f"  Interface: {dev_info.get('interface_number', 'N/A')}")
            print(f"  Usage Page: {hex(dev_info.get('usage_page', 0))}")
            print(f"  Usage: {hex(dev_info.get('usage', 0))}")
            
            try:
                temp_device = hid.device()
                temp_device.open_path(dev_info['path'])
                
                packet = [0x06, 0x08, 0x00, 0x00, 0x01, 0x00, 0x7a, 0x01]
                
                # Red data for first 10 LEDs, off for rest
                test_data = [255, 0, 0] * 10 + [0, 0, 0] * (self.num_leds - 10)
                packet.extend(test_data)
                packet.extend([0] * (520 - len(packet)))
                
                print(f"  Sending test packet ({len(packet)} bytes)...")
                
                try:
                    result = temp_device.send_feature_report(packet)
                    print(f"  Feature report result: {result}")
                    
                    time.sleep(0.5)
                    
                    response = input(f"  Did you see red lights on interface {i}? (y/n): ").lower().strip()
                    
                    if response == 'y' or response == 'yes':
                        print(f"Interface {i} works! Saving configuration...")
                        
                        clear_packet = packet.copy()
                        clear_packet[8:8 + self.num_leds * 3] = [0] * (self.num_leds * 3)
                        temp_device.send_feature_report(clear_packet)
                        
                        temp_device.close()
                        
                        self.config_manager.set('device_path', dev_info['path'].decode('utf-8') if isinstance(dev_info['path'], bytes) else dev_info['path'])
                        self.config_manager.set('vendor_id', self.VENDOR_ID)
                        self.config_manager.set('product_id', self.PRODUCT_ID)
                        self.config_manager.set('saved_at', time.time())
                        
                        return dev_info['path']
                    else:
                        print(f"  Interface {i} doesn't control RGB lighting")
                        
                except Exception as e:
                    print(f"  Feature report failed: {e}")
                
                temp_device.close()
                
            except Exception as e:
                print(f"  Interface {i} failed to open: {e}")
        
        print("No working interface found!")
        return None

    def verify_saved_interface(self, device_path: str) -> bool:
        try:
            print(f"Verifying saved interface: {device_path}")
            device_path_bytes = device_path.encode('utf-8') if isinstance(device_path, str) else device_path
            temp_device = hid.device()
            temp_device.open_path(device_path_bytes)
            
            # Test packet
            packet = [0x06, 0x08, 0x00, 0x00, 0x01, 0x00, 0x7a, 0x01]
            packet.extend([0] * (self.num_leds * 3))
            packet.extend([0] * (520 - len(packet)))
            written = temp_device.send_feature_report(packet)
            temp_device.close()

            if not written or written <= 0:
                print("Saved interface opened but rejected the report; re-detecting.")
                return False

            print("Saved interface verified!")
            return True
        except Exception as e:
            print(f"Saved interface verification failed: {e}")
            return False

    def is_present(self) -> bool:
        """
        Whether the keyboard is plugged in, regardless of whether it can be opened.

        @returns True if the OS enumerates the device.
        """
        return bool(hid.enumerate(self.VENDOR_ID, self.PRODUCT_ID))

    def can_open_any_interface(self) -> bool:
        """
        Whether at least one of the keyboard's interfaces can be opened.

        Enumeration succeeds without any special privileges, but opening does
        not, so this distinguishes "device unplugged" from "access denied" --
        and lets us skip the interactive interface scan, which would otherwise
        prompt once per interface for a failure that is never going to change.

        @returns True if any interface opened successfully.
        """
        for dev_info in hid.enumerate(self.VENDOR_ID, self.PRODUCT_ID):
            try:
                probe = hid.device()
                probe.open_path(dev_info['path'])
                probe.close()
                return True
            except Exception:
                continue
        return False

    def connect(self, force_find: bool = False) -> bool:

        if not self.is_present():
            print("No Aula F87 Pro found. Connect it over USB -- wireless mode "
                  "does not expose the RGB interface.")
            return False

        warning = sharing_warning()
        if warning:
            print(warning)

        if not self.can_open_any_interface():
            print("The keyboard is connected, but the OS refused to open its "
                  "HID interface.")
            print()
            print(permission_hint())
            return False

        if not force_find and not self.device_path:
            saved_path = self.config_manager.get('device_path')
            if saved_path and self.verify_saved_interface(saved_path):
                self.device_path = saved_path

        if force_find or not self.device_path:
            # Try auto-detection first (non-interactive)
            self.device_path = self.auto_find_interface()
            if not self.device_path:
                # Fall back to interactive search
                self.device_path = self.find_working_interface()
                if not self.device_path:
                    return False
        
        try:
            self.device = hid.device()
            device_path_bytes = self.device_path.encode('utf-8') if isinstance(self.device_path, str) else self.device_path
            self.device.open_path(device_path_bytes)
            print(f"Connected to Aula F87 Pro on path: {self.device_path}")
            return True
        except Exception as e:
            print(f"Failed to connect to working interface: {e}")
            print()
            print(permission_hint())
            self.device = None
            self.device_path = None
            return False
        
    def disconnect(self):
        if self.device:
            print("Disconnecting from keyboard.")
            self.device.close()
            self.device = None
            
    
    def send_rgb(self, rgb_data: list) -> bool:
        if not self.device:
            print("Error: Device not connected. Cannot send RGB data.")
            return False
        
        try:
            packet = [0x06, 0x08, 0x00, 0x00, 0x01, 0x00, 0x7A, 0x01]
            
            expected_len = self.num_leds * 3
            if len(rgb_data) != expected_len:
                if len(rgb_data) < expected_len:
                    rgb_data.extend([0] * (expected_len - len(rgb_data)))
                else:
                    rgb_data = rgb_data[:expected_len]
                                   
            packet.extend(rgb_data)
            packet.extend([0] * (520 - len(packet)))

            self.device.send_feature_report(packet)
            return True
        
        except hid.HIDException as e:
            print(f"HID Error: Failed to send RGB data packet: {e}")
            return False

        except Exception as e:
            print(f"Error: Failed to send RGB data packet: {e}")
            return False

    def turn_off(self) -> bool:
        """Turns all LEDs off."""
        print("Device: Turning all lights off.")
        rgb_data_off = [0] * (self.num_leds * 3)
        return self.send_rgb(rgb_data_off)
        
    def set_solid_color(self, r: int, g: int, b: int, duration: float = 0.0, should_stop=None) -> bool:
        """
        Sets all LEDs to a solid color.
        If duration is 0.0 (default), the color is persistent until interrupted.
        If duration > 0.0, the color is set for that many seconds, then lights turn off.
        """
        print(f"Device: Setting solid color RGB({r},{g},{b}), duration: {'infinite' if duration == 0.0 else str(duration)+'s'}")
        rgb_data_initial = []
        for _ in range(self.num_leds):
            rgb_data_initial.extend([r, g, b])
        
        if not self.send_rgb(rgb_data_initial):
            print("Device Error: Failed to set initial solid color.")
            return False
        
        if duration == 0.0: 
            try:
                while True:
                    if should_stop and should_stop():
                        return True
                    self.send_rgb(rgb_data_initial)
                    # Check periodically (every 0.1s) to allow fast response, send keepalive every 1s
                    for _ in range(10):
                        if should_stop and should_stop():
                            return True
                        time.sleep(0.1)
            except KeyboardInterrupt:
                print("\nDevice: Solid color effect interrupted by user.")
                self.turn_off()
                raise 
        else: #
            try:
                start_time = time.time()
                current_elapsed_time = 0
                

                while current_elapsed_time < duration:
                    current_elapsed_time = time.time() - start_time
                    self.send_rgb(rgb_data_initial)
                    time.sleep(1)
                
                print(f"Device: Solid color duration ({duration}s) ended.")
                self.turn_off()
            except KeyboardInterrupt:
                print("\nDevice: Timed solid color effect interrupted by user.")
                self.turn_off()
                raise 
        return True
        
    
    def breathing_effect(self, r: int, g: int, b: int, duration: float = 0.0, base_rgb_data: list = None, should_stop=None):
        
        import math 
        if base_rgb_data:
             print(f"Device: Breathing effect (Custom Pattern), duration: {'infinite' if duration == 0.0 else str(duration)+'s'}")
        else:
             print(f"Device: Breathing effect RGB({r},{g},{b}), duration: {'infinite' if duration == 0.0 else str(duration)+'s'}")

        try:
            start_time = time.time()
            while True:
                if should_stop and should_stop():
                    break
                    
                current_elapsed_time = time.time() - start_time
                
                if duration != 0.0 and current_elapsed_time >= duration:
                    print(f"Device: Breathing effect duration ({duration}s) ended.")
                    break 
                
                brightness_speed_factor = 1.5 
                brightness = (math.sin(current_elapsed_time * brightness_speed_factor) + 1) / 2

                frame_rgb_data = []
                
                if base_rgb_data:
                    for i in range(0, len(base_rgb_data), 3):
                        if i + 2 < len(base_rgb_data):
                            br = base_rgb_data[i]
                            bg = base_rgb_data[i+1]
                            bb = base_rgb_data[i+2]
                            frame_rgb_data.extend([int(br * brightness), int(bg * brightness), int(bb * brightness)])
                        else:
                             frame_rgb_data.extend([0, 0, 0])
                else:
                    current_r = int(r * brightness)
                    current_g = int(g * brightness)
                    current_b = int(b * brightness)
                    for _ in range(self.num_leds):
                        frame_rgb_data.extend([current_r, current_g, current_b])
                
                if not self.send_rgb(frame_rgb_data):
                    print("Device Error: Failed to send frame for breathing effect. Stopping.")
                    break 
                
                time.sleep(0.05) 

        except KeyboardInterrupt:
            print("\nDevice: Breathing effect interrupted by user.")
            raise 
        finally:
            if duration > 0.0 and (time.time() - start_time >= duration): # Check if it completed naturally
                 self.turn_off()


    def test_sequence(self):
        print("Device: Running RGB test sequence...")
        colors_to_test = {
            "Red": (255, 0, 0), "Green": (0, 255, 0),
            "Blue": (0, 0, 255), "White": (255, 255, 255),
        }
        original_duration_behavior = True 
        
        for name, (r_val,g_val,b_val) in colors_to_test.items():
            print(f"Device Test: Setting color {name}")
            temp_rgb_data = []
            for _ in range(self.num_leds):
                temp_rgb_data.extend([r_val, g_val, b_val])
            if not self.send_rgb(temp_rgb_data):
                print(f"Device Test: Failed to set {name}")
                self.turn_off()
                return
            time.sleep(1) 
        
        print("Device Test: Turning lights off.")
        self.turn_off()
        print("Device Test: Sequence completed.")

    def set_pywal_solid(self, colors: list, duration: float = 0.0) -> bool:
        """Set keyboard to pywal accent color."""
        if not colors or len(colors) < 2:
            print("Error: Not enough pywal colors")
            return False

        # Use accent color (color 1)
        r, g, b = colors[1]
        print(f"Device: Setting pywal accent color RGB({r},{g},{b})")
        return self.set_solid_color(r, g, b, duration)

    def create_gradient_data(self, colors: list) -> list:
        if not colors or len(colors) < 6:
             return None
        
        row_colors = [colors[i] for i in range(1, 7)]
        rows = [
            [0, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96],
            [1, 7, 13, 19, 25, 31, 37, 43, 49, 55, 61, 67, 73, 79, 85, 91, 97],
            [2, 8, 14, 20, 26, 32, 38, 44, 50, 56, 62, 68, 74, 80, 86, 92, 98],
            [3, 9, 15, 21, 27, 33, 39, 45, 51, 57, 63, 69, 81],
            [4, 10, 16, 22, 28, 34, 40, 46, 52, 58, 64, 82, 94],
            [5, 11, 17, 35, 53, 59, 65, 83, 89, 95, 101],
        ]
        
        rgb_data = [0] * (self.num_leds * 3)
        for row_idx, row_keys in enumerate(rows):
            r, g, b = row_colors[row_idx]
            for key_idx in row_keys:
                if key_idx < self.num_leds:
                    rgb_data[key_idx * 3] = r
                    rgb_data[key_idx * 3 + 1] = g
                    rgb_data[key_idx * 3 + 2] = b
        return rgb_data

    def set_pywal_gradient(self, colors: list, duration: float = 0.0, should_stop=None) -> bool:
        """Set keyboard rows to different pywal colors."""
        if not colors or len(colors) < 6:
            print("Error: Not enough pywal colors for gradient")
            return False

        rgb_data = self.create_gradient_data(colors)
        if not rgb_data:
             return False

        print(f"Device: Setting pywal gradient, duration: {'infinite' if duration == 0.0 else str(duration)+'s'}")

        if duration == 0.0:
            try:
                while True:
                    if should_stop and should_stop():
                        return True
                    self.send_rgb(rgb_data)
                    # Check periodically (every 0.1s)
                    for _ in range(10):
                        if should_stop and should_stop():
                            return True
                        time.sleep(0.1)
            except KeyboardInterrupt:
                print("\nDevice: Gradient effect interrupted.")
                self.turn_off()
                raise
        else:
            try:
                start_time = time.time()
                while (time.time() - start_time) < duration:
                    self.send_rgb(rgb_data)
                    time.sleep(1)
                self.turn_off()
            except KeyboardInterrupt:
                print("\nDevice: Gradient effect interrupted.")
                self.turn_off()
                raise

        return True

    def render_theme_frame(self, theme: Theme, elapsed: float) -> list:
        """
        Build one flat RGB buffer for a theme at a point in time.

        LEDs with no mapped physical position stay dark -- the F87 Pro reports
        102 LED slots but only 87 of them sit under a key.

        @param theme - The theme to sample.
        @param elapsed - Seconds since the effect started.
        @returns A flat [r, g, b, r, g, b, ...] buffer of num_leds * 3 values.
        """
        rgb_data = [0] * (self.num_leds * 3)
        for led_index, (row, column) in self.KEY_POSITIONS.items():
            if led_index >= self.num_leds:
                continue
            red, green, blue = theme.color_at(row, column, elapsed)
            offset = led_index * 3
            rgb_data[offset] = red
            rgb_data[offset + 1] = green
            rgb_data[offset + 2] = blue
        return rgb_data

    def run_theme(self, theme: Theme, duration: float = 0.0,
                  should_stop: Optional[Callable[[], bool]] = None) -> bool:
        """
        Play an animated theme on the keyboard.

        The keyboard holds no state of its own, so every frame must be pushed
        over USB; static themes are re-sent at a slow keep-alive rate instead of
        the full frame rate.

        @param theme - The theme to play.
        @param duration - Seconds to run; 0 runs until interrupted.
        @param should_stop - Optional predicate polled each frame to stop early.
        @returns True if the theme ran to completion or was asked to stop.
        """
        frame_interval = 1.0 / theme.frames_per_second
        static = is_static(theme)
        label = "static" if static else f"{theme.frames_per_second} fps"
        print(f"Device: Playing theme '{theme.name}' ({label}), "
              f"duration: {'infinite' if duration == 0.0 else str(duration) + 's'}")

        static_frame = self.render_theme_frame(theme, 0.0) if static else None
        start_time = time.time()

        try:
            while True:
                if should_stop and should_stop():
                    return True

                elapsed = time.time() - start_time
                if duration != 0.0 and elapsed >= duration:
                    print(f"Device: Theme duration ({duration}s) ended.")
                    self.turn_off()
                    return True

                frame = static_frame if static else self.render_theme_frame(theme, elapsed)
                if not self.send_rgb(list(frame)):
                    print("Device Error: Failed to send theme frame. Stopping.")
                    return False

                time.sleep(frame_interval)

        except KeyboardInterrupt:
            print(f"\nDevice: Theme '{theme.name}' interrupted by user.")
            raise

    def run_reactive(self, base_theme: Theme, bubble_field, duration: float = 0.0,
                     frames_per_second: int = 60,
                     should_stop: Optional[Callable[[], bool]] = None) -> bool:
        """
        Play a moving theme and raise a bubble wherever a key is pressed.

        The base animates underneath while keystroke bubbles are composited on
        top, so the board is never still and every frame must be sent.

        Themes with a `reactive_surge` are also driven by typing energy: their
        clock runs faster and their colours brighten while keys are being hit.

        @param base_theme - The moving theme painted underneath.
        @param bubble_field - A BubbleField fed by a key listener.
        @param duration - Seconds to run; 0 runs until interrupted.
        @param frames_per_second - Frame rate for both base and bubbles.
        @param should_stop - Optional predicate polled each frame to stop early.
        @returns True when the effect ended cleanly.
        """
        frame_interval = 1.0 / frames_per_second
        print(f"Device: Reactive mode on a moving '{base_theme.name}' base "
              f"({frames_per_second} fps). Type to raise bubbles.")

        start_time = time.time()
        surge = getattr(base_theme, "reactive_surge", 0.0)
        # The theme's own clock. It runs ahead of wall time while typing energy
        # is high, which speeds the animation up without any jump when the
        # energy changes.
        theme_clock = 0.0
        previous_frame_time = start_time

        try:
            while True:
                if should_stop and should_stop():
                    return True

                now = time.time()
                elapsed = now - start_time

                if duration != 0.0 and elapsed >= duration:
                    print(f"Device: Reactive duration ({duration}s) ended.")
                    self.turn_off()
                    return True

                drive = 1.0 + surge * bubble_field.energy(now) if surge else 1.0
                theme_clock += (now - previous_frame_time) * drive
                previous_frame_time = now

                base_frame = self.render_theme_frame(base_theme, theme_clock)
                if drive > 1.0:
                    base_frame = [min(255, int(channel * drive)) for channel in base_frame]
                frame = bubble_field.render(base_frame, now)

                if not self.send_rgb(list(frame)):
                    print("Device Error: Failed to send reactive frame. Stopping.")
                    return False

                time.sleep(frame_interval)

        except KeyboardInterrupt:
            print("\nDevice: Reactive mode interrupted by user.")
            raise
