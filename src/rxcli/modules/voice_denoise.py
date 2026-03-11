"""Voice De-noise module automation.

ML-based noise reduction optimized for dialogue and music.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .. import ax as ax_mod
from ..rx import RX, RXError, RENDER_TIMEOUT, POLL_INTERVAL

logger = logging.getLogger("rxcli")

NAME = "voice_denoise"
TOTAL_STEPS = 5


def run(
    rx: RX,
    params: dict,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Run Voice De-noise on the currently active file in RX.

    Params:
        threshold: Threshold in dB, -20.0 to 10.0 (default: -2.0).
        reduction: Max reduction in dB, 0.0 to 20.0 (default: 12.0).
        adaptive: Enable adaptive mode (default: true).
        optimize: "dialogue" or "music" (default: "dialogue").
        filter_type: "surgical" or "gentle" (default: "gentle").
    """
    preset = params.get("preset")
    threshold = params.get("threshold")
    reduction = params.get("reduction")
    adaptive = params.get("adaptive")
    optimize = params.get("optimize")
    filter_type = params.get("filter_type")

    def progress(stage: str, step: int):
        if on_progress:
            on_progress(stage, step, TOTAL_STEPS)

    start_time = time.time()

    # 1. Open Voice De-noise module
    progress("opening_module", 1)
    win = rx.open_module("Voice De-noise...")
    if win is None:
        raise RXError("Failed to open Voice De-noise module window")
    time.sleep(0.5)

    # 2. Load preset and/or set sliders
    progress("setting_parameters", 2)
    if preset:
        rx.load_preset(win, preset)

    if threshold is not None:
        threshold = float(threshold)
        thresh_slider = win.find(desc="Threshold [dB]")
        if thresh_slider:
            logger.info("Setting threshold: %s dB", threshold)
            actual = thresh_slider.set_slider_value(threshold)
            logger.info("Threshold set to: %s", actual)
            time.sleep(0.2)

    if reduction is not None:
        reduction = float(reduction)
        red_slider = win.find(desc="Reduction [dB]")
        if red_slider:
            logger.info("Setting reduction: %s dB", reduction)
            actual = red_slider.set_slider_value(reduction)
            logger.info("Reduction set to: %s", actual)
            time.sleep(0.2)

    if threshold is not None or reduction is not None:
        ax_mod.send_escape()
        time.sleep(0.3)

    # 3. Set toggle options (only if explicitly provided)
    progress("setting_options", 3)

    if adaptive is not None:
        adaptive_btn = win.find(desc="Adaptive Mode")
        if adaptive_btn:
            is_on = adaptive_btn.value == 1.0
            if adaptive and not is_on:
                logger.info("Enabling adaptive mode")
                adaptive_btn.press()
                time.sleep(0.2)
            elif not adaptive and is_on:
                logger.info("Disabling adaptive mode")
                adaptive_btn.press()
                time.sleep(0.2)

    if optimize is not None:
        optimize = optimize.lower()
        if optimize == "dialogue":
            btn = win.find(desc="Dialogue")
            if btn and btn.value != 1.0:
                logger.info("Setting optimize for: Dialogue")
                btn.press()
                time.sleep(0.2)
        elif optimize == "music":
            btn = win.find(desc="Music")
            if btn and btn.value != 1.0:
                logger.info("Setting optimize for: Music")
                btn.press()
                time.sleep(0.2)

    if filter_type is not None:
        filter_type = filter_type.lower()
        if filter_type == "surgical":
            btn = win.find(desc="Surgical")
            if btn and btn.value != 1.0:
                logger.info("Setting filter type: Surgical")
                btn.press()
                time.sleep(0.2)
        elif filter_type == "gentle":
            btn = win.find(desc="Gentle")
            if btn and btn.value != 1.0:
                logger.info("Setting filter type: Gentle")
                btn.press()
                time.sleep(0.2)

    # 4. Click Apply and wait for completion
    progress("rendering", 4)
    # Re-find window after button manipulation
    win = rx.find_window("Voice De-noise")
    if win is None:
        raise RXError("Voice De-noise window disappeared")

    undo_before = rx.undo_entries()
    logger.info("Applying Voice De-noise...")

    apply_btn = win.find(desc="Apply")
    if apply_btn and apply_btn.enabled:
        apply_btn.press()
    else:
        raise RXError("Apply button not available")

    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        undo_now = rx.undo_entries()
        if "Voice De-noise" in undo_now and "Voice De-noise" not in undo_before:
            logger.info("Voice De-noise complete")
            break
    else:
        raise RXError("Timed out waiting for Voice De-noise to complete")

    # 5. Close module
    progress("done", 5)
    win_check = rx.find_window("Voice De-noise")
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
    if threshold is not None:
        overrides["threshold"] = threshold
    if reduction is not None:
        overrides["reduction"] = reduction
    if adaptive is not None:
        overrides["adaptive"] = adaptive
    if optimize is not None:
        overrides["optimize"] = optimize
    if filter_type is not None:
        overrides["filter_type"] = filter_type
    if overrides:
        result["parameters"] = overrides
    return result
