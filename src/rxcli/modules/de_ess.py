"""De-ess module automation.

Reduces sibilance (harsh "s" and "sh" sounds) in dialogue and vocal recordings.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .. import ax as ax_mod
from ..rx import RX, RXError, RENDER_TIMEOUT, POLL_INTERVAL

logger = logging.getLogger("rxcli")

NAME = "de_ess"
TOTAL_STEPS = 5


def run(
    rx: RX,
    params: dict,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Run De-ess on the currently active file in RX.

    Params:
        preset: Load a preset by exact name.
        algorithm: "classic" or "spectral" (default: module's current setting).
        threshold: Threshold in dB (default: module's current setting).
        cutoff_freq: Cutoff frequency in Hz (default: module's current setting).
        spectral_shaping: Spectral shaping percentage, 0-100 (only in spectral mode).
        spectral_tilt: Spectral tilt, -1.0 to 1.0 (only in spectral mode).
        speed: "fast" or "slow" (default: module's current setting).
        absolute: Enable absolute mode (bool).
    """
    preset = params.get("preset")
    algorithm = params.get("algorithm")
    threshold = params.get("threshold")
    cutoff_freq = params.get("cutoff_freq")
    spectral_shaping = params.get("spectral_shaping")
    spectral_tilt = params.get("spectral_tilt")
    speed = params.get("speed")
    absolute = params.get("absolute")

    def progress(stage: str, step: int):
        if on_progress:
            on_progress(stage, step, TOTAL_STEPS)

    start_time = time.time()

    # 1. Open De-ess module
    progress("opening_module", 1)
    win = rx.open_module("De-ess...")
    if win is None:
        raise RXError("Failed to open De-ess module window")
    time.sleep(0.5)

    # 2. Load preset
    progress("setting_options", 2)
    if preset:
        rx.load_preset(win, preset)

    # Set algorithm (must be before spectral-only sliders)
    if algorithm is not None:
        algorithm = algorithm.lower()
        if algorithm == "classic":
            btn = win.find(desc="Classic")
            if btn and btn.value != 1.0:
                logger.info("Setting algorithm: Classic")
                btn.press()
                time.sleep(0.3)
        elif algorithm == "spectral":
            btn = win.find(desc="Spectral")
            if btn and btn.value != 1.0:
                logger.info("Setting algorithm: Spectral")
                btn.press()
                time.sleep(0.3)

    if speed is not None:
        speed = speed.lower()
        if speed == "fast":
            btn = win.find(desc="Fast")
            if btn and btn.value != 1.0:
                logger.info("Setting speed: Fast")
                btn.press()
                time.sleep(0.2)
        elif speed == "slow":
            btn = win.find(desc="Slow")
            if btn and btn.value != 1.0:
                logger.info("Setting speed: Slow")
                btn.press()
                time.sleep(0.2)

    if absolute is not None:
        abs_btn = win.find(desc="Absolute CheckBox")
        if abs_btn:
            is_on = abs_btn.value == 1.0
            if absolute and not is_on:
                logger.info("Enabling absolute mode")
                abs_btn.press()
                time.sleep(0.2)
            elif not absolute and is_on:
                logger.info("Disabling absolute mode")
                abs_btn.press()
                time.sleep(0.2)

    # 3. Set sliders
    progress("setting_parameters", 3)
    if threshold is not None:
        threshold = float(threshold)
        slider = win.find(desc="Threshold [dB]")
        if slider:
            logger.info("Setting threshold: %s dB", threshold)
            actual = slider.set_slider_value(threshold)
            logger.info("Threshold set to: %s", actual)
            time.sleep(0.2)

    if cutoff_freq is not None:
        cutoff_freq = float(cutoff_freq)
        slider = win.find(desc="Cutoff freq [Hz]")
        if slider:
            logger.info("Setting cutoff frequency: %s Hz", cutoff_freq)
            actual = slider.set_slider_value(cutoff_freq)
            logger.info("Cutoff frequency set to: %s", actual)
            time.sleep(0.2)

    if spectral_shaping is not None:
        spectral_shaping = float(spectral_shaping)
        slider = win.find(desc="Spectral shaping [%]")
        if slider and slider.enabled:
            logger.info("Setting spectral shaping: %s%%", spectral_shaping)
            actual = slider.set_slider_value(spectral_shaping)
            logger.info("Spectral shaping set to: %s", actual)
            time.sleep(0.2)

    if spectral_tilt is not None:
        spectral_tilt = float(spectral_tilt)
        slider = win.find(desc="Spectral tilt")
        if slider and slider.enabled:
            logger.info("Setting spectral tilt: %s", spectral_tilt)
            actual = slider.set_slider_value(spectral_tilt)
            logger.info("Spectral tilt set to: %s", actual)
            time.sleep(0.2)

    if any(v is not None for v in [threshold, cutoff_freq, spectral_shaping, spectral_tilt]):
        ax_mod.send_escape()
        time.sleep(0.3)

    # 4. Click Apply and wait for completion
    progress("rendering", 4)
    win = rx.find_window("De-ess")
    if win is None:
        raise RXError("De-ess window disappeared")

    undo_before = rx.undo_entries()
    logger.info("Applying De-ess...")

    apply_btn = win.find(desc="Apply")
    if apply_btn and apply_btn.enabled:
        apply_btn.press()
    else:
        raise RXError("Apply button not available")

    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        undo_now = rx.undo_entries()
        if "De-ess" in undo_now and "De-ess" not in undo_before:
            logger.info("De-ess complete")
            break
    else:
        raise RXError("Timed out waiting for De-ess to complete")

    # 5. Close module
    progress("done", 5)
    win_check = rx.find_window("De-ess")
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
    if algorithm is not None:
        overrides["algorithm"] = algorithm
    if threshold is not None:
        overrides["threshold"] = threshold
    if cutoff_freq is not None:
        overrides["cutoff_freq"] = cutoff_freq
    if spectral_shaping is not None:
        overrides["spectral_shaping"] = spectral_shaping
    if spectral_tilt is not None:
        overrides["spectral_tilt"] = spectral_tilt
    if speed is not None:
        overrides["speed"] = speed
    if absolute is not None:
        overrides["absolute"] = absolute
    if overrides:
        result["parameters"] = overrides
    return result
