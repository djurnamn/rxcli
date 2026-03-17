"""Mouth De-click module automation.

Removes mouth clicks, lip smacks, and similar artifacts from dialogue recordings.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .. import ax as ax_mod
from ..rx import RX, RXError, RENDER_TIMEOUT, POLL_INTERVAL

logger = logging.getLogger("rxcli")

NAME = "mouth_declick"
TOTAL_STEPS = 4


def run(
    rx: RX,
    params: dict,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Run Mouth De-click on the currently active file in RX.

    Params:
        preset: Load a preset by exact name.
        sensitivity: Detection sensitivity 0.0-10.0 (default: 4.0).
        click_widening: Widen detected clicks in ms, 0.0-10.0 (default: 0.0).
        frequency_skew: Bias toward LF or HF clicks, -1.0 to 1.0 (default: 0.0).
    """
    preset = params.get("preset")
    sensitivity = params.get("sensitivity")
    click_widening = params.get("click_widening")
    frequency_skew = params.get("frequency_skew")

    def progress(stage: str, step: int):
        if on_progress:
            on_progress(stage, step, TOTAL_STEPS)

    start_time = time.time()

    # 1. Open Mouth De-click module
    progress("opening_module", 1)
    win = rx.open_module("Mouth De-click...")
    if win is None:
        raise RXError("Failed to open Mouth De-click module window")
    time.sleep(0.5)

    # 2. Load preset and/or set parameters
    progress("setting_parameters", 2)
    if preset:
        rx.load_preset(win, preset)

    if sensitivity is not None:
        sensitivity = float(sensitivity)
        slider = win.find(desc="Sensitivity", role="AXSlider")
        if slider:
            logger.info("Setting sensitivity: %s", sensitivity)
            actual = slider.set_slider_value(sensitivity)
            logger.info("Sensitivity set to: %s", actual)
            time.sleep(0.2)

    if click_widening is not None:
        click_widening = float(click_widening)
        slider = win.find(desc="Click widening [ms]")
        if slider:
            logger.info("Setting click widening: %s ms", click_widening)
            actual = slider.set_slider_value(click_widening)
            logger.info("Click widening set to: %s", actual)
            time.sleep(0.2)

    if frequency_skew is not None:
        frequency_skew = float(frequency_skew)
        slider = win.find(desc="Frequency skew")
        if slider:
            logger.info("Setting frequency skew: %s", frequency_skew)
            actual = slider.set_slider_value(frequency_skew)
            logger.info("Frequency skew set to: %s", actual)
            time.sleep(0.2)

    if sensitivity is not None or click_widening is not None or frequency_skew is not None:
        ax_mod.send_escape()
        time.sleep(0.3)

    # 3. Click Apply and wait for completion
    progress("rendering", 3)
    undo_before = rx.undo_entries()
    logger.info("Applying Mouth De-click...")

    apply_btn = win.find(desc="Apply")
    if apply_btn and apply_btn.enabled:
        apply_btn.press()
    else:
        raise RXError("Apply button not available")

    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        undo_now = rx.undo_entries()
        if "Mouth De-click" in undo_now and "Mouth De-click" not in undo_before:
            logger.info("Mouth De-click complete")
            break
    else:
        raise RXError("Timed out waiting for Mouth De-click to complete")

    # 4. Close module
    progress("done", 4)
    win_check = rx.find_window("Mouth De-click")
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
    if sensitivity is not None:
        overrides["sensitivity"] = sensitivity
    if click_widening is not None:
        overrides["click_widening"] = click_widening
    if frequency_skew is not None:
        overrides["frequency_skew"] = frequency_skew
    if overrides:
        result["parameters"] = overrides
    return result
