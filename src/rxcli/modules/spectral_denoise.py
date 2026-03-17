"""Spectral De-noise module automation.

Broadband noise reduction using spectral analysis. Supports adaptive mode
(no training needed) and manual mode (requires a noise profile learned from
a selection).
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from .. import ax as ax_mod
from ..rx import RX, RXError, RENDER_TIMEOUT, POLL_INTERVAL

logger = logging.getLogger("rxcli")

NAME = "spectral_denoise"
TOTAL_STEPS = 5


def run(
    rx: RX,
    params: dict,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Run Spectral De-noise on the currently active file in RX.

    By default uses adaptive mode which requires no training step.

    Params:
        preset: Load a preset by exact name.
        threshold: Threshold in dB (default: module's current setting).
        reduction: Suppression/reduction amount in dB (default: module's current setting).
        artifact_control: Artifact control 0.0-20.0 (default: module's current setting).
        smoothing: Smoothing amount (default: module's current setting).
        quality: Quality level — 0=A (best), 1=B, 2=C, 3=D (fast).
        adaptive: Enable adaptive mode (bool, default: true).
    """
    preset = params.get("preset")
    threshold = params.get("threshold")
    reduction = params.get("reduction")
    artifact_control = params.get("artifact_control")
    smoothing = params.get("smoothing")
    quality = params.get("quality")
    adaptive = params.get("adaptive")

    def progress(stage: str, step: int):
        if on_progress:
            on_progress(stage, step, TOTAL_STEPS)

    start_time = time.time()

    # 1. Open Spectral De-noise module
    progress("opening_module", 1)
    win = rx.open_module("Spectral De-noise...")
    if win is None:
        raise RXError("Failed to open Spectral De-noise module window")
    time.sleep(0.5)

    # 2. Load preset and/or set options
    progress("setting_options", 2)
    if preset:
        rx.load_preset(win, preset)

    # Adaptive mode — set before sliders since it affects what's needed
    if adaptive is not None:
        adaptive_btn = win.find(desc="Adaptive Mode CheckBox")
        if adaptive_btn:
            is_on = adaptive_btn.value == 1.0
            if adaptive and not is_on:
                logger.info("Enabling adaptive mode")
                adaptive_btn.press()
                time.sleep(0.3)
            elif not adaptive and is_on:
                logger.info("Disabling adaptive mode")
                adaptive_btn.press()
                time.sleep(0.3)

    # 3. Set sliders
    progress("setting_parameters", 3)
    if threshold is not None:
        threshold = float(threshold)
        slider = win.find(desc="Threshold Linked")
        if slider:
            logger.info("Setting threshold: %s dB", threshold)
            actual = slider.set_slider_value(threshold)
            logger.info("Threshold set to: %s", actual)
            time.sleep(0.2)

    if reduction is not None:
        reduction = float(reduction)
        slider = win.find(desc="Suppression Linked")
        if slider:
            logger.info("Setting reduction: %s dB", reduction)
            actual = slider.set_slider_value(reduction)
            logger.info("Reduction set to: %s", actual)
            time.sleep(0.2)

    if artifact_control is not None:
        artifact_control = float(artifact_control)
        slider = win.find(desc="Artifact control")
        if slider:
            logger.info("Setting artifact control: %s", artifact_control)
            actual = slider.set_slider_value(artifact_control)
            logger.info("Artifact control set to: %s", actual)
            time.sleep(0.2)

    if smoothing is not None:
        smoothing = float(smoothing)
        slider = win.find(desc="Smoothing")
        if slider:
            logger.info("Setting smoothing: %s", smoothing)
            actual = slider.set_slider_value(smoothing)
            logger.info("Smoothing set to: %s", actual)
            time.sleep(0.2)

    if quality is not None:
        quality = float(quality)
        slider = win.find(desc="Quality", role="AXSlider")
        if slider:
            logger.info("Setting quality: %s", quality)
            actual = slider.set_slider_value(quality)
            logger.info("Quality set to: %s", actual)
            time.sleep(0.2)

    if any(v is not None for v in [threshold, reduction, artifact_control, smoothing, quality]):
        ax_mod.send_escape()
        time.sleep(0.3)

    # 4. Click Apply and wait for completion
    progress("rendering", 4)
    win = rx.find_window("Spectral De-noise")
    if win is None:
        raise RXError("Spectral De-noise window disappeared")

    undo_before = rx.undo_entries()
    logger.info("Applying Spectral De-noise...")

    apply_btn = win.find(desc="Apply")
    if apply_btn and apply_btn.enabled:
        apply_btn.press()
    else:
        raise RXError(
            "Apply button not available. In non-adaptive mode, ensure a "
            "noise profile has been learned first (select noise, click Train)."
        )

    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        undo_now = rx.undo_entries()
        if "Spectral De-noise" in undo_now and "Spectral De-noise" not in undo_before:
            logger.info("Spectral De-noise complete")
            break
    else:
        raise RXError("Timed out waiting for Spectral De-noise to complete")

    # 5. Close module
    progress("done", 5)
    win_check = rx.find_window("Spectral De-noise")
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
    if artifact_control is not None:
        overrides["artifact_control"] = artifact_control
    if smoothing is not None:
        overrides["smoothing"] = smoothing
    if quality is not None:
        overrides["quality"] = quality
    if adaptive is not None:
        overrides["adaptive"] = adaptive
    if overrides:
        result["parameters"] = overrides
    return result
