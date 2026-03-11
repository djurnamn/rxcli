"""Normalize module automation.

Normalizes the audio to a target peak level.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .. import ax as ax_mod
from ..rx import RX, RXError, RENDER_TIMEOUT, POLL_INTERVAL

logger = logging.getLogger("rxcli")

NAME = "normalize"
TOTAL_STEPS = 4


def run(
    rx: RX,
    params: dict,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Normalize the currently active file in RX.

    Params:
        target_level: Target peak level in dBFS, -20.0 to 0.0 (default: 0.0).
    """
    preset = params.get("preset")
    target_level = params.get("target_level")

    def progress(stage: str, step: int):
        if on_progress:
            on_progress(stage, step, TOTAL_STEPS)

    start_time = time.time()

    # 1. Open Normalize module
    progress("opening_module", 1)
    win = rx.open_module("Normalize...")
    if win is None:
        raise RXError("Failed to open Normalize module window")
    time.sleep(0.5)

    # 2. Load preset and/or set parameters
    progress("setting_parameters", 2)
    if preset:
        rx.load_preset(win, preset)

    if target_level is not None:
        target_level = float(target_level)
        slider = win.find(desc="Target peak level [dBFS]")
        if slider:
            logger.info("Setting target peak level: %s dBFS", target_level)
            actual = slider.set_slider_value(target_level)
            logger.info("Target peak level set to: %s", actual)
            ax_mod.send_escape()
            time.sleep(0.3)

    # 3. Click Apply and wait for completion
    progress("rendering", 3)
    undo_before = rx.undo_entries()
    logger.info("Applying Normalize...")

    apply_btn = win.find(desc="Apply")
    if apply_btn and apply_btn.enabled:
        apply_btn.press()
    else:
        raise RXError("Apply button not available")

    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        undo_now = rx.undo_entries()
        if "Normalize" in undo_now and "Normalize" not in undo_before:
            logger.info("Normalize complete")
            break
    else:
        raise RXError("Timed out waiting for Normalize to complete")

    # 4. Close module
    progress("done", 4)
    win_check = rx.find_window("Normalize")
    if win_check:
        close_btn = win_check.attr("AXCloseButton")
        if close_btn:
            ax_mod.AXElement(close_btn).press()
            time.sleep(0.3)

    elapsed = time.time() - start_time
    result = {"module": NAME, "duration_seconds": round(elapsed, 1)}
    if preset:
        result["preset"] = preset
    if target_level is not None:
        result["parameters"] = {"target_level": target_level}
    return result
