# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- `pulse` theme: an equalizer driven by the Mac's sound output, captured
  through a small ScreenCaptureKit helper (`audio_tap.swift`). Bars adjust to
  the track's volume, bass beats send rings and shift the colours, and with
  no sound it plays a rainbow equalizer show with a heartbeat.
- `Theme.listens_to_audio` and `Theme.on_audio_levels(levels)` hooks, fed by
  `audio.SystemAudioListener`.
- `forge` theme: a simulation where each keypress strikes the metal, heating
  that key and throwing sparks. Steady typing builds momentum that heats the
  whole board to white-hot. Left idle, it plays a fire show of its own.
- `sandfall` theme: falling-sand physics where each keypress drops a grain from
  that key. It's the first simulation theme (`SimulationTheme` in
  `simulation.py`), where the board keeps state and keypresses feed into it.
- `Theme.on_key_press(row, column)` hook, called under `--reactive`.

### Changed
- The theme contract and colour helpers moved to `theme_base.py`. `themes.py`
  re-exports them, so existing imports still work.

## [0.1.0] - 2025-05-31
### Added
- Initial release of `aula-f87pro-cli`.
- Basic functionality to set solid color, turn off lights, and run breathing effect.
- Device connection and interface finding logic.
- Configuration management for saving device path.
- CLI argument parsing for different modes.