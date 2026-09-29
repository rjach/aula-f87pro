# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
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