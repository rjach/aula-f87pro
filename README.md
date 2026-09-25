# Aula F 87 Pro CLI Controller

> **Personal keyboard lighting customization.** This is my personal fork of [Ahorts/aula-f87pro](https://github.com/Ahorts/aula-f87pro), extended with themes, reactive lighting, and a macOS HID backend for my own Aula F87 Pro setup.
## UPDATE
This project may no longer be needed since the functionalities offered by this project have now be added to openRGB. 

## DISCLAIMER
**THIS PROJECT DOES NOT REVERSE ENGINEER THE COMPLETE COMMUNICATION PROTOCOL OF THE AULA F87 PRO KEYBOARD. IT IS A SIMPLE SCRIPT DESIGNED TO SEND RGB DATA TO THE KEYBOARD FOR LIGHTING CONTROL. CURRENTLY, THIS SCRIPT HAS NO CAPABILITY TO SAVE CONFIGURATIONS ON THE KEYBOARD ITSELF; ALL EFFECTS ARE APPLIED IN REAL-TIME VIA SOFTWARE.**

A command-line interface (CLI) tool to control the RGB lighting of the Aula F87 Pro keyboard on **Linux and macOS**.

## Limitations

*   **Wired Mode Only:** Currently, this tool has only been confirmed to work with the Aula F87 Pro keyboard when connected via a USB cable (wired mode). Efforts to control RGB lighting in wireless mode (e.g., 2.4GHz or Bluetooth) have so far been unsuccessful.

## Features

*   **Animated per-key themes** (`aurora`, `nebula`, `tide`, `ember`, `spectrum`, `dusk`).
*   **Terminal preview** of any theme, so you can pick one without the keyboard attached.
*   Set solid colors for all LEDs.
*   Apply a breathing light effect.
*   Turn off all keyboard lights.
*   Run a test sequence to check RGB functionality.
*   Automatically find and save the correct HID interface for RGB control.
*   Manage configuration via `~/.aula_f87_config.json`.
*   Parse color inputs in various formats (named colors, hex codes, RGB strings).
*   List available predefined color names.
*   **Pywal integration** - sync keyboard colors with your terminal/wallpaper color scheme.
*   Adjustable theme brightness (`--brightness 1-100`).

## Typical Use Cases

1.   **Dynamic Desktop Color Sync:** Use this CLI tool as a backend for a separate script that monitors your desktop environment's dominant colors (e.g., from your wallpaper or active window). The external script can then call `aula-f87pro --color <detected_color>` to dynamically update your keyboard lighting to match your desktop theme.

2.   **Custom Lighting Effects:** While this tool provides basic effects like solid color and breathing, it can serve as a foundation for more complex custom lighting patterns. If the built-in effects aren't sufficient, you can create your own scripts that repeatedly call `aula-f87pro` with different color arguments in sequence or create new functions to generate unique animations. This will require some programming and tinkering on your part.

## Installation

1.  **Prerequisites:**
    *   Python 3.9 or higher
    *   `pip` (Python package installer)
    *   `libhidapi-hidraw0` (or equivalent for your distribution) for `hidapi` to work.
        ```bash
        sudo apt-get update
        sudo apt-get install libhidapi-hidraw0
        ```

2.  **Clone the repository (if you haven't already):**
    ```bash
    git clone https://github.com/Ahorts/aula-f87pro.git
    cd aula-f87pro
    ```

3.  **Install the CLI tool:**
    It's recommended to install in a virtual environment.
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install .
    ```
    Alternatively, for an editable install (changes in code are reflected immediately):
    ```bash
    pip install -e .
    ```

### Alternative Installation for Global Access

If you intend to call `aula-f87pro` from other scripts or want it available globally without activating a virtual environment:

*   **Using `pipx` (Recommended for user-level global tools):**

    1.  **Install `pipx`:**
        *   On many systems, especially those that manage Python packages strictly (like Arch Linux, recent Debian/Ubuntu versions), you should install `pipx` using your system's package manager to avoid "externally managed environment" errors.

            *   For Arch Linux:

                ```bash
                sudo pacman -S python-pipx
                ```

            *   For Debian/Ubuntu (if available in repositories, check your version):
                ```bash
                sudo apt install pipx
                ```

            *   If your distribution doesn't package `pipx` or the above methods don't work, you might try the official bootstrap method, but prefer your system package manager if possible:

                ```bash
                python3 -m pip install --user pipx
                ```

        *   After installing `pipx`, ensure its scripts directory is in your PATH:
            ```bash
            python3 -m pipx ensurepath
            ```
            You may need to open a new terminal or re-login for this change to take effect.
    2.  **Install `aula-f87pro` with `pipx`:**
        From the `aula-f87pro` project directory:
        ```bash
        pipx install .
        ```
        This installs `aula-f87pro` in an isolated environment but makes the command available in your user's PATH.

*   **System-Wide Installation (Use with caution):**
    ```bash
    sudo pip install .
    ```
    This makes `aula-f87pro` available to all users but installs it into the system Python environment. This is generally discouraged on systems with "externally managed" Python environments as it might conflict with the system package manager or lead to an inconsistent state. Prefer `pipx` or virtual environments.

##
## Udev Rules for Non-Root Access (Linux)

To use this tool without `sudo`, you need to set up udev rules to grant your user permission to access the keyboard's HID interface.

1.  Create a new udev rule file (replace nano with your editor of choice):
    ```bash
    sudo nano /etc/udev/rules.d/99-aula-f87pro.rules
    ```

2.  Add the following line to the file:
    ```
    SUBSYSTEM=="hidraw", ATTRS{idVendor}=="258a", ATTRS{idProduct}=="010c", MODE="0666"
    ```
    *Note: `MODE="0666"` grants access to all users. For a more secure setup, you can use `GROUP="plugdev"` (or another group your user belongs to) and `MODE="0660"`.*

3.  Save the file and exit the editor.

4.  Reload the udev rules and trigger them:
    ```bash
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    ```

5.  Unplug and replug your Aula F87 Pro keyboard.


* NOTE: If all else fails, you can add a NOPASSWD rule for script execution

## Usage

The primary command is `aula-f87pro`.

**First-time Setup (Finding the Interface):**
```bash
aula-f87pro --find-interface
```

**Basic Usage:**
```bash
aula-f87pro --color red              # Set solid color
aula-f87pro --color "#FF6600"        # Hex color
aula-f87pro --breathing blue         # Breathing effect
aula-f87pro --off                    # Turn off
aula-f87pro --test                   # Test sequence
aula-f87pro --theme aurora           # Animated theme
aula-f87pro --list-themes            # See all themes
```


## Themes

Animated, per-key lighting patterns. Every theme is computed on the host and
streamed to the board, so a theme lasts only as long as the command runs.

```bash
aula-f87pro --list-themes
aula-f87pro --theme aurora                 # runs until Ctrl+C
aula-f87pro --theme dusk --brightness 60   # dimmer, low glare
aula-f87pro --theme tide --duration 30     # stop after 30s and turn off
```

| Theme      | Look |
| ---------- | ---- |
| `supernova` | Spinning prismatic galaxy: spiral arms wheel around the board while shockwaves burst from a white-hot core. |
| `reactor`  | Hyperactive plasma that fires its own sparks and rings several times a second, so it never sits still. With `--reactive`, each keystroke throws a board-wide shockwave and typing speeds up and brightens the plasma. |
| `rojan`    | **ROJAN** in still neon pixel letters; every other key stays unlit. With `--reactive`, keystroke bubbles are the only thing that moves. |
| `aurora`   | Slow northern-lights ribbons: teal, mint, cyan and violet. **Default.** |
| `nebula`   | Magenta and indigo clouds with drifting starlight. |
| `tide`     | Ocean swell rolling across the board in deep blue and cyan. |
| `ember`    | Warm coals rising from the bottom row into cooling smoke. |
| `spectrum` | Smooth full-hue rainbow sweeping diagonally. |
| `dusk`     | Still sunset gradient. Static, low glare, good for long sessions. |

### Previewing without the keyboard

`--preview` renders the real key layout in your terminal using 24-bit colour.
Useful for choosing a theme, and for checking the tool works before sorting out
device permissions.

```bash
aula-f87pro --theme nebula --preview
```

### Keeping a theme running

Because the keyboard holds no lighting state, the process has to stay alive.
Run it in the background:

```bash
nohup aula-f87pro --theme aurora --duration 0 >/dev/null 2>&1 &
```

On macOS, `scripts/com.aula.f87pro.theme.plist` is a ready launchd agent that
restores your theme at login; installation notes are in the file's comments.

## macOS

The tool works on macOS over USB, with one extra step.

### Install

`hidapi` replaces the Linux-only `hidraw` binding:

```bash
brew install hidapi
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

### Grant Input Monitoring (required, once)

The F87 Pro advertises a keyboard usage page, so macOS refuses to let *any*
process open its HID interface until the calling app is trusted. Without this
you will see `open failed`.

1.  **System Settings -> Privacy & Security -> Input Monitoring**
2.  Enable the terminal you run the command from (Terminal, iTerm2, Ghostty,
    WezTerm, VS Code...). Click `+` and add it from `/Applications` if it is
    not listed.
3.  **Fully quit and reopen that terminal** - the permission is only picked up
    on a fresh launch.

Then confirm:

```bash
aula-f87pro --find-interface
aula-f87pro --theme aurora
```

Note that the permission is attached to the terminal *application*, not to this
tool, so each terminal you use needs it. Udev rules do not apply on macOS.

## Pywal Integration

Sync your keyboard RGB with your pywal color scheme.

**Usage:**
```bash
aula-f87pro --pywal                  # Use pywal accent color
aula-f87pro --pywal gradient         # Each row gets a different pywal color
```

**Auto-sync with wal command:**

Add this to your `~/.bashrc` or `~/.zshrc`:
```bash
wal() {
    /usr/bin/wal "$@"
    pkill -f "aula-f87pro" 2>/dev/null
    nohup /path/to/aula-f87pro/.venv/bin/aula-f87pro --pywal --duration 0 >/dev/null 2>&1 &
    disown
}
```

Now every time you run `wal -i wallpaper.jpg`, your keyboard will automatically update to match.
