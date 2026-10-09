# Aula F87 Pro Lighting

My personal lighting setup for the Aula F87 Pro keyboard: animated per-key
themes, lighting that reacts to keystrokes, and a shell helper that keeps a
theme running in the background on macOS.

This is a fork of [Ahorts/aula-f87pro](https://github.com/Ahorts/aula-f87pro),
a small CLI for sending RGB data to the F87 Pro. The original handles solid
colours, breathing, and pywal sync on Linux. This fork adds:

- 17 animated themes, each computed per key from its real position on the board
- `pulse`, a theme that lights the board to whatever the Mac is playing (macOS)
- `--reactive`, which lights up a ripple from each key you press (macOS)
- macOS support through `hidapi`, with the Input Monitoring setup documented
- `--preview`, which draws any theme in your terminal so you don't need the keyboard
- `--brightness`, and a `useKeyTheme` zsh helper plus a launchd agent to keep a theme running

> **Heads-up:** OpenRGB now supports the F87 Pro. If you only want basic
> lighting control, use that. This repo is for the custom effects.

## How it works

The keyboard stores no lighting of its own. Every effect is computed on the
computer and streamed to the board over USB, so **the lights only change while
the process is running**. That's why themes run until you press Ctrl+C, and why
there's a helper to run them in the background.

It only works in **wired mode**. Controlling the lights over 2.4 GHz or
Bluetooth hasn't worked so far.

## Install

Requires Python 3.9+.

```bash
git clone https://github.com/rjach/aula-f87pro.git
cd aula-f87pro
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### macOS

```bash
brew install hidapi
```

macOS won't let any process open the keyboard's HID interface until the app
running it has **Input Monitoring** permission. Without it you get `open failed`.

1. Go to **System Settings → Privacy & Security → Input Monitoring**.
2. Turn it on for your terminal (Terminal, iTerm2, Ghostty, WezTerm, VS Code…).
   Use `+` to add the terminal if it isn't listed.
3. **Quit the terminal completely and reopen it.** The permission only applies
   after a fresh launch.

`--reactive` needs the same permission, because it listens for which keys are
pressed. It only uses each key's position. Nothing you type is recorded.

### Linux

Install `libhidapi-hidraw0` (or your distro's equivalent). To run without
`sudo`, add a udev rule:

```bash
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="258a", ATTRS{idProduct}=="010c", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-aula-f87pro.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then unplug the keyboard and plug it back in. For a tighter setup, use
`GROUP="plugdev"` and `MODE="0660"`.

### First run

Find and save the HID interface that controls the lights:

```bash
aula-f87pro --find-interface
```

## Themes

```bash
aula-f87pro --list-themes
aula-f87pro --theme                        # default theme (flow)
aula-f87pro --theme aurora                 # runs until Ctrl+C
aula-f87pro --theme dusk --brightness 60   # dimmer
aula-f87pro --theme tide --duration 30     # stop after 30 seconds
aula-f87pro --theme reactor --reactive     # reacts to typing (macOS)
aula-f87pro --theme pulse                  # reacts to system sound (macOS)
aula-f87pro --theme nebula --preview       # show in the terminal, no keyboard needed
```

| Theme       | Look |
| ----------- | ---- |
| `flow`      | A different colour on each key, flowing across the board. **Default.** |
| `aurora`    | Northern-lights ribbons in teal, cyan, and violet. |
| `nebula`    | Magenta and indigo clouds with drifting starlight. |
| `tide`      | Ocean swell rolling across the board in deep blue and cyan. |
| `ember`     | Warm coals rising from the bottom row into cooling smoke. |
| `inferno`   | Turbulent, white-hot fire rising up the board. |
| `spectrum`  | A smooth rainbow sweeping diagonally. |
| `synthwave` | Neon magenta and cyan bands with a bright sweep passing over them. |
| `matrix`    | Green code rain with bright leading characters. |
| `voltage`   | White-blue electric arcs across a dark board. |
| `supernova` | A spinning rainbow galaxy with shockwaves bursting from a white-hot core. |
| `forge`     | Typing is the hammer. Each keypress strikes hot and throws sparks, and steady typing heats the board to white-hot. When you're not typing it plays a fire show of its own. Pair it with `--reactive`. |
| `pulse`     | An equalizer that moves to whatever the Mac is playing. Bass sits in the middle and treble at the edges. Each beat sends a ring out from the spacebar and shifts the colours. With no sound it plays its own rainbow equalizer with a heartbeat. |
| `reactor`   | Plasma that sparks on its own and surges while you type. |
| `sandfall`  | Falling sand. Each keypress drops a grain from that key. Grains pile up, and a full bottom row flashes and clears. Pair it with `--reactive`. |
| `rojan`     | **ROJAN** in neon pixel letters on an unlit board. Pair it with `--reactive`. |
| `dusk`      | A still sunset gradient. Low glare, good for long sessions. |

### Reactive mode

`--reactive` dims the theme into a backdrop, and each keypress sends a ripple
out from that key. Some themes adjust this: `reactor` hits harder the faster
you type, and in `rojan` the ripples are the only thing that moves.

`sandfall` works differently from the other themes. They all compute each key's
colour from its position and the time. `sandfall` runs a small simulation with
its own state, and each keypress becomes an input to it: a grain dropped from
the key you pressed. The ripples shrink to a small splash so the pile stays
visible. Without `--reactive`, grains still drift in from the top on their own.

`forge` is also a simulation, built around momentum. Each keypress heats the
key you hit and throws sparks upward. Heat spreads, rises and cools within
about a second. Steady typing also stokes the forge bed along the bottom row,
so a long stretch of focused work turns the board red, then orange, then
white-hot at the bed. Left alone, it plays a show: flames churn up from the bottom, a hammer rhythm
wanders the board throwing sparks, and a bright wave rises every few seconds.
It pauses while you type and comes back 2.5 seconds after you stop.

### Sound-reactive mode (`pulse`)

`pulse` listens to the Mac's audio output: music, videos, games, anything
that plays sound. It doesn't use the microphone. A small Swift helper
(`src/f87pro/audio_tap.swift`) captures the output through ScreenCaptureKit,
splits it into 12 frequency bands, and passes only those levels to Python.
No audio is recorded or saved.

- **First run** builds the helper with `swiftc` and caches it in
  `~/Library/Caches/aula-f87pro/`. If `swiftc` is missing, run
  `xcode-select --install`.
- **Permission:** macOS asks for **Screen & System Audio Recording** for your
  terminal. Allow it under **System Settings → Privacy & Security → Screen &
  System Audio Recording**, then quit and reopen the terminal. macOS asks for
  this because the system audio API is part of screen capture. The helper
  asks for the smallest video it can (2×2 pixels, once a second) and ignores it.
- **Volume:** the bars adjust to the level of what's playing, so quiet and
  loud tracks both fill the board.
- **No sound:** when nothing is playing, or the audio can't be captured, the
  theme plays its idle show. When sound starts, the real spectrum fades in.
  After about 1.5 seconds of silence, the show fades back.
- `--reactive` works too. Keypresses add a short flash and a small ring.

## Keeping a theme running

### `useKeyTheme` (zsh)

`scripts/useKeyTheme.zsh` runs one background instance, remembers your theme
between shells, and replaces the old instance whenever you switch.

```bash
# in ~/.zshrc
export AULA_F87_HOME="$HOME/path/to/aula-f87pro"
source "$AULA_F87_HOME/scripts/useKeyTheme.zsh"
```

```bash
useKeyTheme                   # start the saved theme in reactive mode
useKeyTheme --theme=nebula    # switch to a theme and save it
useKeyTheme --list
useKeyTheme --status
useKeyTheme --stop            # stop, leaving the lights as they are
useKeyTheme --off             # stop and turn the lights off
```

### launchd (macOS)

`scripts/com.aula.f87pro.theme.plist` is a launchd agent that starts a theme
when you log in. The comments at the top of the file explain how to install it.

### Anything else

```bash
nohup aula-f87pro --theme aurora --duration 0 >/dev/null 2>&1 &
```

## Other commands

These come from the original project and still work:

```bash
aula-f87pro --color red                # also "#FF6600" or "255,102,0"
aula-f87pro --breathing blue --duration 30
aula-f87pro --off
aula-f87pro --test
aula-f87pro --list-colors
aula-f87pro --show-config              # saved in ~/.aula_f87_config.json
aula-f87pro --pywal                    # pywal accent colour
aula-f87pro --pywal gradient --watch   # a different pywal colour on each row, updates when pywal changes
```

## Project layout

```
src/f87pro/
  cli.py          argument parsing and dispatch
  device.py       connecting to the keyboard and streaming frames
  hid_backend.py  picks hidapi or hidraw, macOS permission hints
  layout.py       physical key positions for all 102 LEDs
  themes.py       the themes (colour maths only, no hardware access)
  reactive.py     keypress ripples and the macOS key listener
  keycodes.py     maps macOS keycodes to LEDs
  preview.py      terminal preview
scripts/          useKeyTheme.zsh, launchd agent
tests/            theme and frame tests
```

Themes only turn a key's position and the elapsed time into a colour, so you
can test and preview them without the keyboard.

```bash
python -m pytest
```

## Credits and licence

The original CLI is by [Ahorts](https://github.com/Ahorts/aula-f87pro).
This project doesn't implement the keyboard's full protocol. It sends RGB
frames and can't save settings to the keyboard. MIT licensed, see `LICENCE`.
