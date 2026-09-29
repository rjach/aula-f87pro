# Aula F87 Pro Lighting

My personal lighting setup for the Aula F87 Pro keyboard: animated per-key
themes, lighting that reacts to keystrokes, and a shell helper that keeps a
theme running in the background on macOS.

This is a fork of [Ahorts/aula-f87pro](https://github.com/Ahorts/aula-f87pro),
a small CLI for sending RGB data to the F87 Pro. The original handles solid
colours, breathing, and pywal sync on Linux. This fork adds:

- 14 animated themes, each computed per key from its real position on the board
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
