"""De-bleed module automation.

Removes microphone bleed by learning the relationship between a bleed source
track and the target track, then applying reduction.

Requires a reference file (the bleed source) to be specified in params.
The reference is opened/closed by this module — the pipeline only needs to
have the target file open.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

from .. import ax as ax_mod
from ..rx import RX, RXError, RENDER_TIMEOUT, POLL_INTERVAL

logger = logging.getLogger("rxcli")

# Module metadata
NAME = "debleed"
TOTAL_STEPS = 8


def run(
    rx: RX,
    params: dict,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Run De-bleed on the currently active file in RX.

    The target file must already be open in RX. This module handles
    opening/closing the reference file and the De-bleed panel.

    Params:
        reference: Path to the bleed source track (required).
        reduction: Reduction strength 0.0-8.0 (default: 1.0).
        smoothing: Artifact smoothing 0.0-15.0 (default: 5.0).

    Returns:
        Dict with module result info.
    """
    reference_path = params.get("reference")
    if not reference_path:
        raise RXError("De-bleed requires a 'reference' parameter")
    preset = params.get("preset")
    reduction = params.get("reduction")
    smoothing = params.get("smoothing")

    def progress(stage: str, step: int):
        if on_progress:
            on_progress(stage, step, TOTAL_STEPS)

    start_time = time.time()

    # 1. Open reference file
    progress("opening_reference", 1)
    logger.info("Opening reference file: %s", reference_path)
    rx.open_file(reference_path)
    time.sleep(0.5)

    # Switch back to the target file tab (opening reference made it active)
    # We find the target by checking what was active before
    main = rx.main_window()
    if main:
        tabs = main.find_all(role="AXRadioButton")
        # The target file's tab is typically the second-to-last "File Tab"
        # since the reference was just opened as the last one.
        # We'll verify via the De-bleed module's ActiveTrackName after opening it.

    # 2. Open the De-bleed module
    progress("opening_module", 2)
    debleed_win = rx.open_module("De-bleed...")
    if debleed_win is None:
        raise RXError("Failed to open De-bleed module window")
    time.sleep(0.5)

    # 3. Verify the active track is the target file (not the reference)
    active_track_el = debleed_win.find(desc="ActiveTrackName")
    ref_name = os.path.basename(reference_path)
    if active_track_el:
        active_track = active_track_el.value or ""
        logger.info("Active track: %s", active_track)
        if ref_name in active_track:
            # Wrong track active — switch to the other one
            logger.info("Switching away from reference track")
            if main:
                for tab in main.find_all(role="AXRadioButton"):
                    desc = tab.description or ""
                    if "File Tab" in desc:
                        tab.press()
                        time.sleep(0.5)
                        active_track_el = debleed_win.find(desc="ActiveTrackName")
                        if active_track_el and ref_name not in (active_track_el.value or ""):
                            logger.info("Switched to: %s", active_track_el.value)
                            break

    # 4. Select the bleed source track from the ClipSelectorCombobox
    progress("selecting_source", 3)
    clip_selector = debleed_win.find(desc="ClipSelectorCombobox")
    if clip_selector is None:
        raise RXError("Cannot find bleed source track selector")

    logger.info("Selecting bleed source track: %s", ref_name)
    clip_selector.press()
    time.sleep(0.5)

    popup_win = rx.find_window("ClipSelectorCombobox Popup")
    if popup_win is None:
        raise RXError("Clip selector popup did not appear")

    ref_btn = popup_win.find(title=ref_name, role="AXButton")
    if ref_btn is None:
        available = [c.title for c in popup_win.find_all(role="AXButton")]
        ax_mod.send_escape()
        raise RXError(
            f"Reference track '{ref_name}' not found in clip selector. "
            f"Available: {available}"
        )

    ref_btn.press()
    logger.info("Selected bleed source: %s", ref_name)
    time.sleep(0.5)

    # 5. Load preset and/or set parameters via keyboard arrows
    progress("setting_parameters", 4)
    if preset:
        rx.load_preset(debleed_win, preset)

    if reduction is not None:
        reduction = float(reduction)
        reduction_slider = debleed_win.find(desc="Reduction strength")
        if reduction_slider:
            logger.info("Setting reduction strength: %s", reduction)
            actual = reduction_slider.set_slider_value(reduction)
            logger.info("Reduction strength set to: %s", actual)
            time.sleep(0.2)

    if smoothing is not None:
        smoothing = float(smoothing)
        smoothing_slider = debleed_win.find(desc="Artifact smoothing")
        if smoothing_slider:
            logger.info("Setting artifact smoothing: %s", smoothing)
            actual = smoothing_slider.set_slider_value(smoothing)
            logger.info("Artifact smoothing set to: %s", actual)
            time.sleep(0.2)

    if reduction is not None or smoothing is not None:
        # Release keyboard focus from sliders — JUCE swallows AXPress on buttons
        # while a slider has keyboard focus
        ax_mod.send_escape()
        time.sleep(0.3)

    # 6. Click Learn and wait for completion
    progress("learning", 5)
    learn_btn = debleed_win.find(desc="LearnButton")
    if learn_btn is None:
        raise RXError("Cannot find Learn button")

    if not learn_btn.enabled:
        raise RXError(
            "Learn button is disabled. Ensure both files are open and "
            "a bleed source track is selected."
        )

    logger.info("Starting Learn...")
    learn_btn.press()
    time.sleep(1)

    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        db_status = debleed_win.find(desc="DebleedStatusText")
        if db_status:
            val = db_status.value or ""
            if "learned from" in val.lower():
                logger.info("Learn complete: %s", val)
                break
    else:
        raise RXError("Timed out waiting for Learn to complete")

    time.sleep(0.5)

    # 7. Render — click Apply and wait for undo history entry
    progress("rendering", 6)
    # Re-find window in case the AX reference is stale
    debleed_win = rx.find_window("De-bleed")
    if debleed_win is None:
        raise RXError("De-bleed window disappeared before render")

    undo_before = rx.undo_entries()
    logger.info("Rendering De-bleed (undo entries before: %d)...", len(undo_before))

    apply_btn = debleed_win.find(desc="Apply")
    if apply_btn and apply_btn.enabled:
        apply_btn.press()
    else:
        raise RXError("Apply button not available after Learn")

    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        undo_now = rx.undo_entries()
        if "De-bleed" in undo_now and "De-bleed" not in undo_before:
            status = rx.status_text()
            logger.info("De-bleed render complete: %s", status)
            break
    else:
        raise RXError(
            f"Timed out waiting for De-bleed render ({RENDER_TIMEOUT}s). "
            "The file may be very large — consider increasing the timeout."
        )

    # 8. Close De-bleed module (releases sidechain lock) and reference file
    progress("cleanup", 7)
    debleed_win_check = rx.find_window("De-bleed")
    if debleed_win_check:
        close_btn = debleed_win_check.attr("AXCloseButton")
        if close_btn:
            ax_mod.AXElement(close_btn).press()
            logger.info("Closed De-bleed module (sidechain released)")
            time.sleep(0.5)

    rx.close_file(reference_path)
    time.sleep(0.3)

    progress("done", 8)
    elapsed = time.time() - start_time
    result = {
        "module": NAME,
        "reference": reference_path,
        "duration_seconds": round(elapsed, 1),
    }
    if preset:
        result["preset"] = preset
    overrides = {}
    if reduction is not None:
        overrides["reduction"] = reduction
    if smoothing is not None:
        overrides["smoothing"] = smoothing
    if overrides:
        result["parameters"] = overrides
    return result
