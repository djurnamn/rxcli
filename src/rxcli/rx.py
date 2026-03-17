"""RX 11 application controller — manages the RX process and its UI state."""

from __future__ import annotations

import logging
import subprocess
import time

from . import ax

logger = logging.getLogger("rxcli")

RX_APP_NAME = "iZotope RX 11"
RX_BUNDLE_ID = "com.izotope.RX11AudioEditor"
RX_APP_PATH = "/Applications/iZotope RX 11 Audio Editor.app"

# Timeouts (seconds)
LAUNCH_TIMEOUT = 30
FILE_OPEN_TIMEOUT = 30
RENDER_TIMEOUT = 600  # 10 min for long files
POLL_INTERVAL = 0.5


class RXError(Exception):
    """Raised when an RX operation fails."""


class RX:
    """Controller for an iZotope RX 11 Audio Editor instance."""

    def __init__(self):
        self._app: ax.AXElement | None = None
        self._ns_app = None


    # -- Lifecycle ---------------------------------------------------------

    def launch(self) -> None:
        """Launch RX if not running, bring to front, and wait for ready."""
        self._ns_app = ax.find_running_app(RX_APP_NAME)
        if self._ns_app is None:
            # Also try by bundle ID in case the name differs
            self._ns_app = ax.find_running_app_by_bundle(RX_BUNDLE_ID)
        if self._ns_app is None:
            logger.info("Launching RX 11...")
            subprocess.run(["open", "-a", RX_APP_PATH], check=True)
            deadline = time.time() + LAUNCH_TIMEOUT
            while time.time() < deadline:
                self._ns_app = ax.find_running_app(RX_APP_NAME)
                if self._ns_app is None:
                    self._ns_app = ax.find_running_app_by_bundle(RX_BUNDLE_ID)
                if self._ns_app is not None:
                    break
                time.sleep(POLL_INTERVAL)
            else:
                raise RXError("Timed out waiting for RX 11 to launch")
            # Wait for a window to appear (RX loads TF models on startup)
            logger.info("Waiting for RX window...")
            self._app = ax.app_element(self._ns_app)
            deadline2 = time.time() + LAUNCH_TIMEOUT
            while time.time() < deadline2:
                if self.windows():
                    break
                time.sleep(POLL_INTERVAL)
            time.sleep(1)
        else:
            logger.info("RX 11 already running (PID %d)", self._ns_app.processIdentifier())

        self._ns_app.activateWithOptions_(1)  # NSApplicationActivateIgnoringOtherApps
        time.sleep(0.3)
        self._app = ax.app_element(self._ns_app)

        # Dismiss "restore previous session" dialog if present
        self._dismiss_dialogs()

    def quit(self) -> None:
        """Quit RX gracefully."""
        if self._ns_app:
            logger.info("Quitting RX 11...")
            self._ns_app.terminate()
            deadline = time.time() + 10
            while time.time() < deadline:
                if ax.find_running_app(RX_APP_NAME) is None:
                    break
                time.sleep(POLL_INTERVAL)
            self._app = None
            self._ns_app = None

    @property
    def app(self) -> ax.AXElement:
        if self._app is None:
            raise RXError("RX not connected. Call launch() first.")
        return self._app

    # -- Window helpers ----------------------------------------------------

    def windows(self) -> list[ax.AXElement]:
        kids = self.app.attr("AXWindows")
        if kids:
            return [ax.AXElement(w) for w in kids]
        return []

    def main_window(self) -> ax.AXElement | None:
        """Return the main editor window (may be titled with a filename or the default title)."""
        for w in self.windows():
            title = w.title or ""
            # The main window is the one that has the EditorView group
            if w.find(desc="EditorView"):
                return w
        return None

    def find_window(self, title_contains: str) -> ax.AXElement | None:
        for w in self.windows():
            title = w.title or ""
            if title_contains in title:
                return w
        return None

    # -- Menu interaction --------------------------------------------------

    def _menubar(self) -> ax.AXElement:
        mb = self.app.attr("AXMenuBar")
        if mb is None:
            raise RXError("Cannot access menu bar")
        return ax.AXElement(mb)

    def _click_menu(self, *path: str) -> None:
        """Click a menu item by path, e.g. _click_menu("File", "Open...")."""
        mb = self._menubar()
        current_items = mb.children
        for i, name in enumerate(path):
            found = None
            for item in current_items:
                if item.title == name:
                    found = item
                    break
            if found is None:
                raise RXError(f"Menu item not found: {' > '.join(path[:i+1])}")

            found.press()
            time.sleep(0.3)

            if i < len(path) - 1:
                # Descend into submenu
                sub_children = found.children
                if sub_children:
                    # The submenu is usually the first child (an AXMenu)
                    menu = sub_children[0]
                    current_items = menu.children
                else:
                    raise RXError(f"No submenu found under: {name}")

    # -- State reset -------------------------------------------------------

    def _dismiss_welcome(self) -> None:
        """Dismiss the Welcome overlay if present (it's part of the main window)."""
        main = self.main_window()
        if not main:
            return
        # The Welcome overlay has "Getting Started" and "What's New" buttons.
        # If those exist, the overlay is showing. Its X close button is an
        # unnamed AXButton with value=False.
        if not main.find(desc="Getting Started"):
            return
        for btn in main.find_all(role="AXButton"):
            if not btn.description and not btn.title and btn.value is False:
                logger.debug("Dismissing Welcome screen")
                btn.press()
                time.sleep(0.3)
                return

    def reset(self) -> None:
        """Close all files and floating windows, returning RX to a clean state."""
        logger.info("Resetting RX to clean state...")

        # Dismiss the Welcome overlay first (it blocks interaction)
        self._dismiss_welcome()

        # Close any floating/dialog windows that are NOT the main editor window
        skip_windows = set()
        for attempt in range(20):
            windows = self.windows()
            closed_any = False
            for w in windows:
                if w.find(desc="EditorView"):
                    continue  # skip main editor window

                win_id = id(w.ref)
                title = w.title or "(unnamed)"
                if win_id in skip_windows:
                    continue

                logger.debug("Closing floating window: %s", title)

                # Try close button first
                close_btn = w.attr("AXCloseButton")
                if close_btn:
                    ax.AXElement(close_btn).press()
                    time.sleep(0.3)
                    closed_any = True
                    break  # re-scan after closing

                # Some windows (Export, dialogs) have Cancel buttons instead
                cancel = w.find(title="Cancel", role="AXButton")
                if cancel is None:
                    cancel = w.find(desc="Cancel", role="AXButton")
                if cancel:
                    cancel.press()
                    time.sleep(0.3)
                    closed_any = True
                    break

                # Window has no close/cancel mechanism — skip it
                logger.debug("Cannot close window %r, skipping", title)
                skip_windows.add(win_id)

            if not closed_any:
                break

        # Close all open files — may need multiple attempts if dialogs appear
        for close_attempt in range(3):
            time.sleep(0.3)
            try:
                self._click_menu("File", "Close All Files")
                time.sleep(1)
                self._dismiss_dialogs()
                # Check if files are actually closed
                main = self.main_window()
                if main:
                    audio = main.find(desc="Audio Description")
                    if not audio or not audio.value or audio.value.strip() in ("", "|", " | "):
                        break  # files closed successfully
                else:
                    break
            except RXError:
                # "Close All Files" might be disabled if no files are open
                logger.debug("Close All Files not available (no files open)")
                break

        # Verify clean state
        main = self.main_window()
        if main:
            status = main.find(desc="Status Bar Text")
            audio = main.find(desc="Audio Description")
            if audio and audio.value and audio.value.strip() not in ("", "|", " | "):
                logger.warning("Files may still be open after reset: %s", audio.value)
            else:
                logger.info("Reset complete — clean state confirmed")
        else:
            logger.info("Reset complete")

    def _dismiss_dialogs(self) -> None:
        """Dismiss any modal dialogs (save, sidechain warnings, etc.)."""
        for _ in range(10):
            time.sleep(0.3)
            dismissed = False
            for w in self.windows():
                if w.find(desc="EditorView"):
                    continue  # skip main window

                # "Don't Save" on save dialogs
                dont_save = w.find(title="Don't Save", role="AXButton")
                if dont_save:
                    logger.debug("Dismissing save dialog")
                    dont_save.press()
                    dismissed = True
                    break

                # "OK" on warning/info dialogs (e.g., sidechain in use)
                ok_btn = w.find(title="OK", role="AXButton")
                if ok_btn:
                    logger.debug("Dismissing dialog with OK")
                    ok_btn.press()
                    dismissed = True
                    break

                # "No" button
                no_btn = w.find(title="No", role="AXButton")
                if no_btn:
                    logger.debug("Dismissing dialog with No")
                    no_btn.press()
                    dismissed = True
                    break
            if not dismissed:
                break

    # -- File operations ---------------------------------------------------

    def open_file(self, path: str) -> None:
        """Open an audio file in RX using the 'open' CLI command."""
        logger.info("Opening file: %s", path)
        subprocess.run(["open", "-a", RX_APP_PATH, path], check=True)

        # Wait for file to load by watching the status bar or window title
        deadline = time.time() + FILE_OPEN_TIMEOUT
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            main = self.main_window()
            if main:
                status_el = main.find(desc="Status Bar Text")
                if status_el:
                    status = status_el.value or ""
                    if "File opened successfully" in status:
                        logger.info("File loaded: %s", path)
                        return
                    if "error" in status.lower():
                        raise RXError(f"Error opening file: {status}")
        raise RXError(f"Timed out waiting for file to open: {path}")

    def close_file(self, path: str) -> None:
        """Close a specific file by switching to its tab and using File > Close File."""
        import os
        filename = os.path.basename(path)
        main = self.main_window()
        if not main:
            return

        # Find and click the tab for this file
        tabs = main.find_all(role="AXRadioButton")
        for tab in tabs:
            desc = tab.description or ""
            if "File Tab" in desc:
                tab.press()
                time.sleep(0.3)
                # Check if window title matches
                main = self.main_window()
                if main and filename in (main.title or ""):
                    try:
                        self._click_menu("File", "Close File")
                        time.sleep(0.5)
                        self._dismiss_dialogs()
                        logger.info("Closed file: %s", filename)
                    except RXError:
                        pass
                    return

        logger.debug("File tab not found for: %s", filename)

    def close_all_files(self) -> None:
        """Close all open files without saving."""
        try:
            self._click_menu("File", "Close All Files")
            time.sleep(0.5)
            self._dismiss_dialogs()
        except RXError:
            pass

    def save_in_place(self) -> None:
        """Save the active file back to its original location using Overwrite Original File."""
        logger.info("Saving file in place (Overwrite Original File)...")
        status_before = self.status_text()
        self._click_menu("File", "Overwrite Original File")

        # Wait for save to complete — status bar changes from whatever it was
        # to something containing "saved", "overw", or "File opened" (after re-load).
        deadline = time.time() + 60
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            status = self.status_text()
            if status and status != status_before:
                logger.info("Save complete: %s", status)
                return
        raise RXError("Timed out waiting for save to complete")

    # -- Module operations -------------------------------------------------

    def load_preset(self, module_win: ax.AXElement, preset_name: str) -> None:
        """Load a preset by exact name from the module's Preset Manager dropdown.

        Args:
            module_win: The module's floating window (AXElement).
            preset_name: Exact name of the preset (e.g. "Light Bleed").

        Raises:
            RXError: If the preset selector or named preset is not found.
        """
        # The preset popup's desc follows the pattern "<Module> Preset Manager"
        popup = module_win.find(role="AXPopUpButton", title="Presets")
        if popup is None:
            raise RXError("Cannot find Preset Manager in module window")

        # Derive the popup window title from the popup's description
        # e.g. "Normalize Preset Manager" -> "Normalize Preset Manager Popup"
        popup_desc = popup.description or ""
        popup_window_title = f"{popup_desc} Popup"

        logger.info("Loading preset: %s", preset_name)
        popup.press()
        time.sleep(0.5)

        popup_win = self.find_window(popup_window_title)
        if popup_win is None:
            ax.send_escape()
            raise RXError(f"Preset popup window did not appear ({popup_window_title!r})")

        preset_btn = popup_win.find(title=preset_name, role="AXButton")
        if preset_btn is None:
            # Collect available presets for the error message
            available = [
                c.title for c in popup_win.find_all(role="AXButton")
                if c.title and c.title != "[Default]"
            ]
            ax.send_escape()
            raise RXError(
                f"Preset '{preset_name}' not found. "
                f"Available: {available}"
            )

        preset_btn.press()
        time.sleep(0.5)
        logger.info("Preset loaded: %s (popup value: %s)", preset_name, popup.value)

    def open_module(self, module_menu_name: str) -> ax.AXElement | None:
        """Open a module via the Modules menu and return its floating window."""
        logger.info("Opening module: %s", module_menu_name)
        self._click_menu("Modules", module_menu_name)
        time.sleep(1)

        # Find the floating window for this module
        # The window title is usually the module name without "..."
        clean_name = module_menu_name.rstrip(".")
        for w in self.windows():
            title = w.title or ""
            if clean_name.lower() in title.lower():
                return w
        return None

    def render_module(self, module_name: str) -> None:
        """Trigger Modules > Render > <module_name> and wait for completion."""
        logger.info("Rendering module: %s", module_name)
        self._click_menu("Modules", "Render", module_name)

        # Wait for render to complete by monitoring status bar
        deadline = time.time() + RENDER_TIMEOUT
        rendering_started = False
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            main = self.main_window()
            if main:
                status_el = main.find(desc="Status Bar Text")
                if status_el and status_el.value:
                    status = status_el.value
                    if "processing" in status.lower() or "rendering" in status.lower():
                        rendering_started = True
                        continue
                    if rendering_started and ("processed" in status.lower() or "complete" in status.lower() or "ms)" in status):
                        logger.info("Render complete: %s", status)
                        return
                    # Sometimes it goes straight to completion
                    if "processed" in status.lower():
                        logger.info("Render complete: %s", status)
                        return
            if not rendering_started:
                # Check if it already finished (fast render on short files)
                time.sleep(1)
                if main:
                    status_el = main.find(desc="Status Bar Text")
                    if status_el and status_el.value and "processed" in status_el.value.lower():
                        logger.info("Render complete: %s", status_el.value)
                        return
                rendering_started = True  # assume it started

        raise RXError(f"Timed out waiting for render to complete ({RENDER_TIMEOUT}s)")

    # -- Status monitoring -------------------------------------------------

    def status_text(self) -> str:
        """Return the current status bar text."""
        main = self.main_window()
        if main:
            el = main.find(desc="Status Bar Text")
            if el:
                return el.value or ""
        return ""

    def undo_entries(self) -> list[str]:
        """Return the list of undo history entry names."""
        main = self.main_window()
        if not main:
            return []
        radios = main.find_all(role="AXRadioButton")
        return [
            r.description
            for r in radios
            if r.description and "File Tab" not in r.description
        ]

    def wait_for_status(self, text: str, timeout: float = 30) -> str:
        """Poll status bar until it contains the given text. Returns the full status."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.status_text()
            if text.lower() in status.lower():
                return status
            time.sleep(POLL_INTERVAL)
        raise RXError(f"Timed out waiting for status containing: {text!r}")
