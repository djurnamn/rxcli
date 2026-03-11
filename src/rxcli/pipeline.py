"""Pipeline orchestrator — chains module operations on a single file."""

from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Callable

from .rx import RX, RXError

logger = logging.getLogger("rxcli")

# Module registry — maps module names to their run functions.
# Each module's run(rx, params, on_progress) assumes the target file is open.
MODULES: dict[str, object] = {}


def _load_modules():
    """Lazy-load module registry to avoid circular imports."""
    if MODULES:
        return
    from .modules import (
        debleed, normalize, voice_denoise, breath_control,
        mouth_declick, de_ess, spectral_denoise, de_reverb,
    )
    MODULES[debleed.NAME] = debleed.run
    MODULES[normalize.NAME] = normalize.run
    MODULES[voice_denoise.NAME] = voice_denoise.run
    MODULES[breath_control.NAME] = breath_control.run
    MODULES[mouth_declick.NAME] = mouth_declick.run
    MODULES[de_ess.NAME] = de_ess.run
    MODULES[spectral_denoise.NAME] = spectral_denoise.run
    MODULES[de_reverb.NAME] = de_reverb.run


def run_pipeline(
    rx: RX,
    input_path: str,
    output_path: str,
    steps: list[dict],
    on_progress: Callable[[str, str, int, int], None] | None = None,
) -> dict:
    """Run a sequence of modules on a single audio file.

    Args:
        rx: Connected RX controller (already launched).
        input_path: Source audio file.
        output_path: Where to save the processed result.
        steps: List of step dicts, each with "module" and module-specific params.
                e.g. [{"module": "debleed", "reference": "ref.wav", "reduction": 0.8}]
        on_progress: Optional callback(module_name, stage, step, total_steps).

    Returns:
        Dict with pipeline result info.
    """
    _load_modules()

    if not steps:
        raise RXError("Pipeline has no steps")

    # Validate all module names before starting
    for i, step in enumerate(steps):
        module_name = step.get("module")
        if not module_name:
            raise RXError(f"Step {i + 1} is missing 'module' key")
        if module_name not in MODULES:
            available = ", ".join(sorted(MODULES.keys()))
            raise RXError(
                f"Unknown module '{module_name}' in step {i + 1}. "
                f"Available: {available}"
            )

    start_time = time.time()

    def emit(module: str, stage: str, step: int, total: int):
        if on_progress:
            on_progress(module, stage, step, total)

    # 1. Copy input to output path
    emit("pipeline", "copying", 1, 3 + len(steps))
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    shutil.copy2(input_path, output_path)
    logger.info("Copied input to output path: %s", output_path)

    # 2. Open the copy in RX
    emit("pipeline", "opening", 2, 3 + len(steps))
    rx.open_file(output_path)
    time.sleep(0.5)

    # 3. Run each module step
    step_results = []
    for i, step in enumerate(steps):
        module_name = step["module"]
        params = {k: v for k, v in step.items() if k != "module"}
        module_fn = MODULES[module_name]

        emit("pipeline", f"step_{i + 1}_{module_name}", 3 + i, 3 + len(steps))
        logger.info("Pipeline step %d/%d: %s", i + 1, len(steps), module_name)

        # Create a module-level progress callback that wraps the pipeline one
        def make_module_progress(mod_name):
            def module_progress(stage, mod_step, mod_total):
                if on_progress:
                    on_progress(mod_name, stage, mod_step, mod_total)
            return module_progress

        result = module_fn(rx, params, make_module_progress(module_name))
        step_results.append(result)

    # 4. Save the processed file
    emit("pipeline", "saving", 3 + len(steps), 3 + len(steps))
    rx.save_in_place()

    elapsed = time.time() - start_time
    return {
        "status": "success",
        "input": input_path,
        "output": output_path,
        "steps": step_results,
        "duration_seconds": round(elapsed, 1),
    }
