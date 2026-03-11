# rxcli

CLI tool for automating [iZotope RX 11 Audio Editor](https://www.izotope.com/en/products/rx.html) via macOS Accessibility APIs.

Designed for programmatic use from scripts (e.g., REAPER/Lua), CI pipelines, or batch processing workflows. Outputs structured JSON to stdout with human-readable logs on stderr.

## Requirements

- **macOS 13 (Ventura) or later** — tested on macOS 15 (Tahoe). Uses stable Accessibility and CoreGraphics APIs that have been available since macOS 10.9, but the pyobjc dependency requires macOS 13+.
- **Python 3.11+**
- **iZotope RX 11 Audio Editor** (Standard or Advanced) installed at `/Applications/iZotope RX 11 Audio Editor.app`
- **Accessibility permissions** granted to your terminal application (see below)

## Installation

### With pipx (recommended)

[pipx](https://pipx.pypa.io/) installs rxcli in an isolated environment and adds it to your PATH:

```bash
brew install pipx
pipx ensurepath  # one-time: adds ~/.local/bin to PATH
pipx install git+https://github.com/djurnamn/rxcli.git
```

After this, `rxcli` is available globally from any terminal. To upgrade to the latest version:

```bash
pipx upgrade rxcli
```

### For development

```bash
git clone https://github.com/djurnamn/rxcli.git
cd rxcli
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Accessibility permissions

rxcli controls RX through the macOS Accessibility API, which requires explicit user consent. You need to grant Accessibility access to the **terminal application** you run rxcli from.

**System Settings > Privacy & Security > Accessibility** — add your terminal app:

- **Terminal.app** or **iTerm2** — add the app itself
- **VS Code** — add "Visual Studio Code" (the integrated terminal inherits VS Code's permissions)
- **Warp**, **Alacritty**, etc. — add the respective app

On first run, rxcli checks for permissions and will tell you if they're missing.

**Important: understand what you're granting.** macOS Accessibility permissions are granted at the application level, not per-process. This means that once your terminal has Accessibility access, *any command* run from that terminal can read and control UI elements across your Mac — not just rxcli. This is a macOS limitation; there is no way to scope it to a single tool. If this concerns you, consider using a dedicated terminal app for rxcli and only granting Accessibility access to that one.

## Usage

```
rxcli [-v] <command> [options]
```

Global flags:
- `-v, --verbose` — Enable debug-level logging to stderr

### Commands

#### `reset`

Close all files and floating windows, returning RX to a clean state.

```bash
rxcli reset
```

#### `debleed`

Run the De-bleed module to remove microphone bleed between tracks.

```bash
rxcli debleed \
  --input "path/to/track_with_bleed.wav" \
  --reference "path/to/bleed_source.wav" \
  --output "path/to/output.wav" \
  --reduction 1.0 \
  --smoothing 5.0
```

**Required arguments:**

| Flag | Description |
|------|-------------|
| `--input, -i` | Audio file to process (the one with bleed) |
| `--reference, -r` | Bleed source track (e.g., the loud mic that's bleeding in) |
| `--output, -o` | Where to save the processed file |

**Optional arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--preset` | | Load a preset by exact name (e.g. `"Light Bleed"`) |
| `--reduction` | | Reduction strength (0.0–8.0) — overrides preset |
| `--smoothing` | | Artifact smoothing (0.0–15.0) — overrides preset |
| `--progress` | off | Emit JSON progress lines to stderr |
| `--reset-before` | on | Reset RX before processing |
| `--no-reset-before` | | Skip pre-processing reset |
| `--reset-after` | on | Reset RX after processing |
| `--no-reset-after` | | Skip post-processing reset |
| `--quit` | off | Quit RX after processing |

**Example with a preset:**

```bash
rxcli debleed \
  -i "session/MIC2.WAV" \
  -r "session/MIC1.WAV" \
  -o "processed/MIC2_debleed.WAV" \
  --preset "Light Bleed"
```

**Example with explicit parameters:**

```bash
rxcli -v debleed \
  -i "session/MIC2.WAV" \
  -r "session/MIC1.WAV" \
  -o "processed/MIC2_debleed.WAV" \
  --reduction 0.8 \
  --smoothing 3.5 \
  --progress \
  --quit
```

#### `pipeline`

Run a multi-step pipeline from a JSON config file. Each step specifies a module and its parameters. The pipeline handles the file lifecycle (copy, open, save) — modules only need to do their processing.

```bash
rxcli pipeline --config pipeline.json --progress
```

**Pipeline JSON format:**

```json
{
  "input": "/path/to/source.wav",
  "output": "/path/to/processed.wav",
  "steps": [
    {
      "module": "debleed",
      "reference": "/path/to/bleed_source.wav",
      "preset": "Light Bleed"
    }
  ]
}
```

Each step object must have a `"module"` key. All other keys are passed as parameters to that module. Steps are executed in order on the same file — the file stays open between steps, and is saved once at the end.

**Presets:** Any step can include a `"preset"` key to load an RX preset by exact name. Explicit parameters in the same step override the preset values. If no preset is specified, explicit parameters are required.

**Multi-step example with presets:**

```json
{
  "input": "session/MIC2.WAV",
  "output": "processed/MIC2.WAV",
  "steps": [
    {"module": "voice_denoise", "preset": "Gentle Cleanup"},
    {"module": "breath_control", "preset": "Medium Breath Suppression", "sensitivity": 70.0},
    {"module": "normalize", "preset": "Normalize to -6 dBFS"}
  ]
}
```

**Multi-step example with explicit parameters:**

```json
{
  "input": "session/MIC2.WAV",
  "output": "processed/MIC2.WAV",
  "steps": [
    {"module": "normalize", "target_level": -3.0},
    {"module": "voice_denoise", "reduction": 10.0},
    {"module": "breath_control", "target_level": -40.0, "sensitivity": 70.0}
  ]
}
```

**Available modules:**

All modules accept an optional `preset` parameter to load an RX preset by exact name. Explicit parameters override preset values.

| Module | Description | Required params | Optional params |
|--------|-------------|-----------------|-----------------|
| `debleed` | Remove mic bleed | `reference` (path) | `preset`, `reduction` (0.0–8.0), `smoothing` (0.0–15.0) |
| `normalize` | Normalize peak level | | `preset`, `target_level` (-20.0–0.0 dBFS) |
| `voice_denoise` | ML noise reduction | | `preset`, `threshold` (-20–10 dB), `reduction` (0–20 dB), `adaptive` (bool), `optimize` ("dialogue"/"music"), `filter_type` ("surgical"/"gentle") |
| `breath_control` | Reduce breath sounds | | `preset`, `target_level` (-100–0 dBFS), `sensitivity` (0–100), `mode` ("target"/"gain") |
| `mouth_declick` | Remove mouth clicks | | `preset`, `sensitivity` (0–10), `click_widening` (0–10 ms), `frequency_skew` (-1.0–1.0) |
| `de_ess` | Reduce sibilance | | `preset`, `algorithm` ("classic"/"spectral"), `threshold` (dB), `cutoff_freq` (Hz), `spectral_shaping` (0–100%), `spectral_tilt` (-1.0–1.0), `speed` ("fast"/"slow"), `absolute` (bool) |
| `spectral_denoise` | Broadband noise reduction | | `preset`, `threshold` (dB), `reduction` (dB), `artifact_control` (0–20), `smoothing`, `quality` (0=best–3=fast), `adaptive` (bool) |
| `de_reverb` | Remove reverb | | `preset`, `reduction` (0–100), `tail_length` (seconds), `artifact_smoothing` (0–20), `enhance_dry` (bool), `band_low`/`band_low_mid`/`band_high_mid`/`band_high` (0–20) |

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--config, -c` | (required) | Path to pipeline JSON config |
| `--progress` | off | Emit JSON progress lines to stderr |
| `--reset-before` | on | Reset RX before processing |
| `--no-reset-before` | | Skip pre-processing reset |
| `--reset-after` | on | Reset RX after processing |
| `--no-reset-after` | | Skip post-processing reset |
| `--quit` | off | Quit RX after processing |

The `debleed` CLI command is shorthand for a single-step pipeline — both use the same underlying pipeline engine.

#### `inspect`

Print the current RX UI state as JSON (useful for debugging).

```bash
rxcli inspect
```

## Output format

### Final result (stdout)

On success:

```json
{
  "status": "success",
  "input": "path/to/input.wav",
  "output": "path/to/output.wav",
  "steps": [
    {
      "module": "voice_denoise",
      "preset": "Gentle Cleanup",
      "duration_seconds": 12.3
    },
    {
      "module": "normalize",
      "preset": "Normalize to -6 dBFS",
      "parameters": {"target_level": -3.0},
      "duration_seconds": 1.2
    }
  ],
  "duration_seconds": 18.7
}
```

On error:

```json
{
  "status": "error",
  "module": "debleed",
  "error": "Description of what went wrong"
}
```

### Progress events (stderr, with `--progress`)

JSON lines emitted during processing, with two levels — pipeline and module:

```json
{"module": "pipeline", "stage": "copying",          "step": 1, "total": 4}
{"module": "pipeline", "stage": "opening",           "step": 2, "total": 4}
{"module": "pipeline", "stage": "step_1_debleed",    "step": 3, "total": 4}
{"module": "debleed",  "stage": "opening_reference",  "step": 1, "total": 8}
{"module": "debleed",  "stage": "opening_module",     "step": 2, "total": 8}
{"module": "debleed",  "stage": "selecting_source",   "step": 3, "total": 8}
{"module": "debleed",  "stage": "setting_parameters", "step": 4, "total": 8}
{"module": "debleed",  "stage": "learning",            "step": 5, "total": 8}
{"module": "debleed",  "stage": "rendering",           "step": 6, "total": 8}
{"module": "debleed",  "stage": "cleanup",             "step": 7, "total": 8}
{"module": "debleed",  "stage": "done",                "step": 8, "total": 8}
{"module": "pipeline", "stage": "saving",             "step": 4, "total": 4}
```

Pipeline `total` is `3 + number_of_steps` (copy, open, one per module step, save). Each module has its own step/total count. When `--progress` is combined with `-v`, both progress JSON and log lines appear on stderr. Parse progress events by looking for lines starting with `{`.

## How it works

rxcli automates RX through three layers:

### `ax.py` — macOS Accessibility API

Low-level wrapper around `AXUIElement` (via pyobjc). Provides:

- **`AXElement`** — Wraps an accessibility element with attribute access (`role`, `description`, `title`, `value`, `enabled`), tree search (`find`, `find_all`), actions (`press`, `set_value`, `set_slider_value`), and child traversal.
- **App discovery** — `find_running_app()`, `find_running_app_by_bundle()`, `app_element()`
- **Keyboard simulation** — `send_key()`, `send_cmd()`, `send_escape()`, `paste_text()` via `CGEvent`

JUCE-based sliders in RX reject direct `AXValue` setting. `set_slider_value()` works around this by focusing the slider and sending arrow key events (Up/Down ±1, Cmd+arrows ±0.1, Shift+arrows ±10), achieving 0.1 precision.

### `rx.py` — RX application controller

Manages the RX process lifecycle and provides high-level operations:

- **Lifecycle** — `launch()` (finds or starts RX, handles recovery dialogs), `quit()`
- **State management** — `reset()` (dismiss welcome overlay, close floating windows, close all files), `_dismiss_dialogs()` (handles save/sidechain/recovery dialogs)
- **File operations** — `open_file()`, `close_file()`, `close_all_files()`, `save_in_place()` (via "Overwrite Original File" menu)
- **Module operations** — `open_module()`, `load_preset()`, `render_module()`
- **Status monitoring** — `status_text()`, `undo_entries()`, `wait_for_status()`

### `pipeline.py` — Pipeline orchestrator

Chains module operations on a single file:

1. Copy input to output path
2. Open the copy in RX
3. For each step: look up the module, call `module.run(rx, params)`
4. Save once via "Overwrite Original File"

Modules are registered in a `MODULES` dict. Each module's `run(rx, params, on_progress)` function assumes the target file is already open and handles its own module-specific concerns (e.g., De-bleed opens/closes its reference file and module panel).

### Modules

All modules follow the same pattern: open the module panel, optionally load a preset, set any explicit parameter overrides, click Apply, wait for the undo history entry, and close the panel.

**`debleed`** — the most complex module. Opens a reference file, opens the De-bleed panel, selects the bleed source track, sets parameters, runs Learn (waits for `DebleedStatusText`), renders, then closes the panel and reference file (releasing the sidechain lock).

**`spectral_denoise`** — supports adaptive mode (no training needed, the default) and manual mode. In manual mode, a noise profile must be learned from a waveform selection before Apply will work.

**`de_reverb`** — works without training. For better results, a reverb profile can be learned from a selection containing a reverb tail (Train button). Band-level reduction controls (low, low-mid, high-mid, high) allow frequency-specific adjustment.

**`de_ess`** — two algorithms: Classic (simple threshold-based) and Spectral (with shaping and tilt controls, enabled only in spectral mode).

**`mouth_declick`**, **`normalize`**, **`voice_denoise`**, **`breath_control`** — straightforward slider/toggle modules with no special lifecycle requirements.

## Important limitations

- **RX must be visible and focused** during automation. The accessibility API and keyboard simulation require the app to be in the foreground. Do not type or use the mouse while rxcli is running — keystrokes will be sent to RX and may disrupt the workflow.
- **Slider precision is ±0.1** due to the keyboard arrow step size. Values like 1.0 and 5.0 are exact; values like 0.55 will round to the nearest 0.1.
- **Sidechain locking** — the De-bleed module locks the reference file while its panel is open. rxcli handles this by closing the module panel before closing files. If RX gets stuck due to a sidechain lock, force quit and restart.
- **Recovery dialog on crash** — if RX crashes or is force-quit, it shows a "Restore previous session" dialog on next launch. rxcli dismisses this automatically.
- **No automated training** — Spectral De-noise (in non-adaptive mode) and De-reverb both have a Train button that learns a noise/reverb profile from a waveform selection. rxcli does not automate this step — making a precise waveform selection requires manual input. Spectral De-noise defaults to adaptive mode which needs no training. De-reverb works without training but produces better results with a learned profile. Use presets or manual training in the RX GUI before running rxcli if a profile is needed.

## Project structure

```
rxcli/
├── LICENSE
├── pyproject.toml
├── README.md
└── src/
    └── rxcli/
        ├── __init__.py
        ├── ax.py            # macOS Accessibility API helpers
        ├── cli.py           # CLI entry point (argparse)
        ├── rx.py            # RX application controller
        ├── pipeline.py      # Pipeline orchestrator
        └── modules/
            ├── __init__.py
            ├── breath_control.py   # Breath Control module
            ├── de_ess.py           # De-ess module
            ├── de_reverb.py        # De-reverb module
            ├── debleed.py          # De-bleed module
            ├── mouth_declick.py    # Mouth De-click module
            ├── normalize.py        # Normalize module
            ├── spectral_denoise.py # Spectral De-noise module
            └── voice_denoise.py    # Voice De-noise module
```
