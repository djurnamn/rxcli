"""De-reverb module automation.

Reduces or removes reverb from recordings. Works without training, but results
improve when a reverb profile is learned from a selection containing reverb tail.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .. import ax as ax_mod
from ..rx import RX, RXError, RENDER_TIMEOUT, POLL_INTERVAL

logger = logging.getLogger("rxcli")

NAME = "de_reverb"
TOTAL_STEPS = 5


def run(
    rx: RX,
    params: dict,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Run De-reverb on the currently active file in RX.

    Params:
        preset: Load a preset by exact name.
        reduction: Reduction strength 0.0-100.0 (default: module's current setting).
        tail_length: Reverb tail length in seconds (default: module's current setting).
        artifact_smoothing: Artifact smoothing 0.0-20.0 (default: module's current setting).
        enhance_dry: Enable "Enhance dry signal" mode (bool).
        band_low: Low band reduction 0.0-20.0.
        band_low_mid: Low-mid band reduction 0.0-20.0.
        band_high_mid: High-mid band reduction 0.0-20.0.
        band_high: High band reduction 0.0-20.0.
    """
    preset = params.get("preset")
    reduction = params.get("reduction")
    tail_length = params.get("tail_length")
    artifact_smoothing = params.get("artifact_smoothing")
    enhance_dry = params.get("enhance_dry")
    band_low = params.get("band_low")
    band_low_mid = params.get("band_low_mid")
    band_high_mid = params.get("band_high_mid")
    band_high = params.get("band_high")

    def progress(stage: str, step: int):
        if on_progress:
            on_progress(stage, step, TOTAL_STEPS)

    start_time = time.time()

    # 1. Open De-reverb module
    progress("opening_module", 1)
    win = rx.open_module("De-reverb...")
    if win is None:
        raise RXError("Failed to open De-reverb module window")
    time.sleep(0.5)

    # 2. Load preset and/or set options
    progress("setting_options", 2)
    if preset:
        rx.load_preset(win, preset)

    if enhance_dry is not None:
        btn = win.find(desc="Enhancement Checkbox")
        if btn:
            is_on = btn.value == 1.0
            if enhance_dry and not is_on:
                logger.info("Enabling enhance dry signal")
                btn.press()
                time.sleep(0.2)
            elif not enhance_dry and is_on:
                logger.info("Disabling enhance dry signal")
                btn.press()
                time.sleep(0.2)

    # 3. Set sliders
    progress("setting_parameters", 3)
    slider_params = [
        (reduction, "Reduction", "reduction"),
        (tail_length, "Tail length [s]", "tail length"),
        (artifact_smoothing, "Artifact smoothing", "artifact smoothing"),
        (band_low, "Low", "band low"),
        (band_low_mid, "Low-mid", "band low-mid"),
        (band_high_mid, "High-mid", "band high-mid"),
        (band_high, "High", "band high"),
    ]

    any_slider_set = False
    for value, desc, label in slider_params:
        if value is not None:
            value = float(value)
            slider = win.find(desc=desc, role="AXSlider")
            if slider:
                logger.info("Setting %s: %s", label, value)
                actual = slider.set_slider_value(value)
                logger.info("%s set to: %s", label.capitalize(), actual)
                time.sleep(0.2)
                any_slider_set = True

    if any_slider_set:
        ax_mod.send_escape()
        time.sleep(0.3)

    # 4. Click Apply and wait for completion
    progress("rendering", 4)
    win = rx.find_window("De-reverb")
    if win is None:
        raise RXError("De-reverb window disappeared")

    undo_before = rx.undo_entries()
    logger.info("Applying De-reverb...")

    apply_btn = win.find(desc="Apply")
    if apply_btn and apply_btn.enabled:
        apply_btn.press()
    else:
        raise RXError("Apply button not available")

    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        undo_now = rx.undo_entries()
        if "De-reverb" in undo_now and "De-reverb" not in undo_before:
            logger.info("De-reverb complete")
            break
    else:
        raise RXError("Timed out waiting for De-reverb to complete")

    # 5. Close module
    progress("done", 5)
    win_check = rx.find_window("De-reverb")
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
    if reduction is not None:
        overrides["reduction"] = float(reduction)
    if tail_length is not None:
        overrides["tail_length"] = float(tail_length)
    if artifact_smoothing is not None:
        overrides["artifact_smoothing"] = float(artifact_smoothing)
    if enhance_dry is not None:
        overrides["enhance_dry"] = enhance_dry
    if band_low is not None:
        overrides["band_low"] = float(band_low)
    if band_low_mid is not None:
        overrides["band_low_mid"] = float(band_low_mid)
    if band_high_mid is not None:
        overrides["band_high_mid"] = float(band_high_mid)
    if band_high is not None:
        overrides["band_high"] = float(band_high)
    if overrides:
        result["parameters"] = overrides
    return result
