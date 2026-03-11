"""Low-level macOS Accessibility API helpers for controlling UI elements."""

from __future__ import annotations

import time
from dataclasses import dataclass

import ApplicationServices as AS
import Cocoa
import Quartz


# ---------------------------------------------------------------------------
# Element wrapper
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AXElement:
    """Thin wrapper around an AXUIElementRef with convenience methods."""

    ref: object  # AXUIElementRef

    # -- Attribute access --------------------------------------------------

    def attr(self, name: str):
        """Return an attribute value, or None on failure."""
        err, val = AS.AXUIElementCopyAttributeValue(self.ref, name, None)
        if err == 0:
            return val
        return None

    @property
    def role(self) -> str | None:
        return self.attr("AXRole")

    @property
    def description(self) -> str | None:
        return self.attr("AXDescription")

    @property
    def title(self) -> str | None:
        return self.attr("AXTitle")

    @property
    def value(self):
        return self.attr("AXValue")

    @property
    def enabled(self) -> bool | None:
        return self.attr("AXEnabled")

    @property
    def children(self) -> list[AXElement]:
        kids = self.attr("AXChildren")
        if kids:
            return [AXElement(k) for k in kids]
        return []

    # -- Actions -----------------------------------------------------------

    def press(self):
        """Perform AXPress action."""
        AS.AXUIElementPerformAction(self.ref, "AXPress")

    def cancel(self):
        AS.AXUIElementPerformAction(self.ref, "AXCancel")

    def set_value(self, value):
        """Set AXValue on this element (works for text fields).

        Note: For JUCE sliders, use set_slider_value() instead — they reject
        direct AXValue setting (error -25200).
        """
        AS.AXUIElementSetAttributeValue(self.ref, "AXValue", value)

    def set_slider_value(self, target: float) -> float:
        """Set a slider to a target value using keyboard arrows.

        JUCE sliders reject direct AXValue setting. Instead, we focus the
        slider via AX, then use arrow keys. Step sizes vary per slider, so
        we probe them dynamically with a single Up keypress.

        Args:
            target: The desired value (in AXValue units).

        Returns:
            The actual value after setting.
        """
        import Quartz as Q

        current = self.value
        if current is None:
            return target

        ax_min = self.attr("AXMinValue") or 0.0
        ax_max = self.attr("AXMaxValue") or 1.0
        target = max(ax_min, min(ax_max, target))

        # Focus the slider
        AS.AXUIElementSetAttributeValue(self.ref, "AXFocused", True)
        time.sleep(0.1)

        UP, DOWN = 126, 125
        CMD = Q.kCGEventFlagMaskCommand
        SHIFT = Q.kCGEventFlagMaskShift

        # Probe the plain-arrow step size. Try Up first; if at max, try Down.
        before = self.value or 0.0
        send_key(UP)
        time.sleep(0.05)
        after = self.value or 0.0
        plain_step = abs(after - before)
        if plain_step > 0:
            send_key(DOWN)  # undo probe
            time.sleep(0.05)
        else:
            # At max — try Down instead
            send_key(DOWN)
            time.sleep(0.05)
            after = self.value or 0.0
            plain_step = abs(after - before)
            if plain_step > 0:
                send_key(UP)  # undo probe
                time.sleep(0.05)

        if plain_step <= 0:
            return self.value or 0.0

        # JUCE arrow key convention: Shift = 10x, plain = 1x, Cmd = 0.1x
        big_step = plain_step * 10
        small_step = plain_step / 10

        steps = [
            (big_step, SHIFT),
            (plain_step, 0),
            (small_step, CMD),
        ]

        for step_size, flags in steps:
            current = self.value or 0.0
            diff = target - current
            n = round(diff / step_size)
            if n == 0:
                continue
            key = UP if n > 0 else DOWN
            for _ in range(abs(n)):
                send_key(key, flags)
            time.sleep(0.1)

        # Fine-tune: correct any remaining drift at the smallest resolution
        current = self.value or 0.0
        remaining = round((target - current) / small_step)
        if remaining != 0:
            key = UP if remaining > 0 else DOWN
            for _ in range(abs(remaining)):
                send_key(key, CMD)
            time.sleep(0.1)

        return self.value or 0.0

    # -- Search ------------------------------------------------------------

    def find(self, *, desc: str | None = None, role: str | None = None,
             title: str | None = None) -> AXElement | None:
        """DFS search for a descendant matching the given criteria."""
        for child in self.children:
            match = True
            if desc is not None and child.description != desc:
                match = False
            if role is not None and child.role != role:
                match = False
            if title is not None and child.title != title:
                match = False
            if match:
                return child
            result = child.find(desc=desc, role=role, title=title)
            if result:
                return result
        return None

    def find_all(self, *, desc: str | None = None, role: str | None = None,
                 title: str | None = None) -> list[AXElement]:
        """DFS search returning all descendants matching the given criteria."""
        results = []
        for child in self.children:
            match = True
            if desc is not None and child.description != desc:
                match = False
            if role is not None and child.role != role:
                match = False
            if title is not None and child.title != title:
                match = False
            if match:
                results.append(child)
            results.extend(child.find_all(desc=desc, role=role, title=title))
        return results

    def find_containing(self, *, desc: str | None = None) -> AXElement | None:
        """DFS search for a descendant whose description contains the string."""
        if desc is None:
            return None
        for child in self.children:
            child_desc = child.description
            if child_desc and desc in child_desc:
                return child
            result = child.find_containing(desc=desc)
            if result:
                return result
        return None

    def __repr__(self):
        parts = [f"role={self.role}"]
        if self.description:
            parts.append(f"desc={self.description!r}")
        if self.title:
            parts.append(f"title={self.title!r}")
        v = self.value
        if v is not None:
            parts.append(f"value={str(v)[:40]!r}")
        return f"AXElement({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Application-level helpers
# ---------------------------------------------------------------------------

def check_accessibility() -> bool:
    """Return True if this process has accessibility permissions."""
    return AS.AXIsProcessTrusted()


def find_running_app(name_fragment: str) -> Cocoa.NSRunningApplication | None:
    """Find a running app whose localizedName contains name_fragment."""
    workspace = Cocoa.NSWorkspace.sharedWorkspace()
    for app in workspace.runningApplications():
        app_name = app.localizedName()
        if app_name and name_fragment in app_name:
            return app
    return None


def find_running_app_by_bundle(bundle_id: str) -> Cocoa.NSRunningApplication | None:
    """Find a running app by its bundle identifier."""
    workspace = Cocoa.NSWorkspace.sharedWorkspace()
    for app in workspace.runningApplications():
        if app.bundleIdentifier() == bundle_id:
            return app
    return None


def app_element(app: Cocoa.NSRunningApplication) -> AXElement:
    """Create an AXElement for a running application."""
    return AXElement(AS.AXUIElementCreateApplication(app.processIdentifier()))


# ---------------------------------------------------------------------------
# Keyboard simulation
# ---------------------------------------------------------------------------

def send_key(keycode: int, flags: int = 0):
    """Send a single keystroke via CGEvents."""
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateCombinedSessionState)
    down = Quartz.CGEventCreateKeyboardEvent(src, keycode, True)
    up = Quartz.CGEventCreateKeyboardEvent(src, keycode, False)
    if flags:
        Quartz.CGEventSetFlags(down, flags)
        Quartz.CGEventSetFlags(up, flags)
    Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, down)
    Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, up)


def send_cmd(keycode: int):
    """Send Cmd+<key>."""
    send_key(keycode, Quartz.kCGEventFlagMaskCommand)


def send_cmd_shift(keycode: int):
    """Send Cmd+Shift+<key>."""
    send_key(keycode, Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift)


def paste_text(text: str):
    """Put text on the pasteboard and send Cmd+V."""
    import AppKit
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
    send_cmd(9)  # 'v'


def send_return():
    send_key(36)


def send_escape():
    send_key(53)
