"""Breath Control module automation.

Reduces or removes breath sounds in dialogue recordings.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .. import ax as ax_mod
from ..rx import RX, RXError, RENDER_TIMEOUT, POLL_INTERVAL

logger = logging.getLogger("rxcli")

NAME = "breath_control"
TOTAL_STEPS = 5


def run(
    rx: RX,
    params: dict,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Run Breath Control on the currently active file in RX.

    Params:
        target_level: Target breath level in dBFS, -100.0 to 0.0 (default: -30.0).
                      Only used in "target" mode.
        sensitivity: Detection sensitivity 0.0-100.0 (default: 60.0).
        mode: "target" or "gain" (default: "target").
              "target" sets breaths to the target level.
              "gain" reduces breaths by target_level dB (acts as gain reduction).
    """
    preset = params.get("preset")
    target_level = params.get("target_level")
    sensitivity = params.get("sensitivity")
    mode = params.get("mode")

    def progress(stage: str, step: int):
        if on_progress:
            on_progress(stage, step, TOTAL_STEPS)

    start_time = time.time()

    # 1. Open Breath Control module
    progress("opening_module", 1)
    win = rx.open_module("Breath Control...")
    if win is None:
        raise RXError("Failed to open Breath Control module window")
    time.sleep(0.5)

    # 2. Load preset and/or set mode
    progress("setting_options", 2)
    if preset:
        rx.load_preset(win, preset)

    if mode is not None:
        mode = mode.lower()
        if mode == "target":
            btn = win.find(desc="Target")
            if btn and btn.value != 1.0:
                logger.info("Setting mode: Target")
                btn.press()
                time.sleep(0.3)
        elif mode == "gain":
            btn = win.find(desc="Gain")
            if btn and btn.value != 1.0:
                logger.info("Setting mode: Gain")
                btn.press()
                time.sleep(0.3)

    # 3. Set sliders (only if explicitly provided)
    progress("setting_parameters", 3)
    if target_level is not None:
        target_level = float(target_level)
        level_slider = win.find(desc="Target level [dBFS]")
        if level_slider:
            logger.info("Setting target level: %s dBFS", target_level)
            actual = level_slider.set_slider_value(target_level)
            logger.info("Target level set to: %s", actual)
            time.sleep(0.2)

    if sensitivity is not None:
        sensitivity = float(sensitivity)
        sens_slider = win.find(desc="Sensitivity")
        if sens_slider:
            logger.info("Setting sensitivity: %s", sensitivity)
            actual = sens_slider.set_slider_value(sensitivity)
            logger.info("Sensitivity set to: %s", actual)
            time.sleep(0.2)

    if target_level is not None or sensitivity is not None:
        ax_mod.send_escape()
        time.sleep(0.3)

    # 4. Click Apply and wait for completion
    progress("rendering", 4)
    # Re-find window
    win = rx.find_window("Breath Control")
    if win is None:
        raise RXError("Breath Control window disappeared")

    undo_before = rx.undo_entries()
    logger.info("Applying Breath Control...")

    apply_btn = win.find(desc="Apply")
    if apply_btn and apply_btn.enabled:
        apply_btn.press()
    else:
        raise RXError("Apply button not available")

    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        undo_now = rx.undo_entries()
        if "Breath Control" in undo_now and "Breath Control" not in undo_before:
            logger.info("Breath Control complete")
            break
    else:
        raise RXError("Timed out waiting for Breath Control to complete")

    # 5. Close module
    progress("done", 5)
    win_check = rx.find_window("Breath Control")
    if win_check:
        close_btn = win_check.attr("AXCloseButton")
        if close_btn:
            ax_mod.AXElement(close_btn).press()
            time.sleep(0.3)

    elapsed = time.time() - start_time
    result = {"module": NAME, "duration_seconds": round(elapsed, 1)}
    if preset:
        result["preset"] = preset
    overrides = {}
    if target_level is not None:
        overrides["target_level"] = target_level
    if sensitivity is not None:
        overrides["sensitivity"] = sensitivity
    if mode is not None:
        overrides["mode"] = mode
    if overrides:
        result["parameters"] = overrides
    return result
