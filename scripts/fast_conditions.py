#!/usr/bin/env python3

"""Device conditions for fastDeviceTest: `network_condition` and `low_power` steps.

Both expand into ordinary Settings steps the runner already knows (checked on an iPhone 15 Plus,
iOS 26.6.1), so they work in a flow and in `do`. A condition switched on is remembered per
iPhone and switched off again when the flow ends (PASS or FAIL), at `fastDeviceTest stop`, or by
`fastDeviceTest conditions off`: Network Link Conditioner survives app restarts and makes every
later run on a shared phone look broken.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTINGS = "com.apple.Preferences"
NETWORK_PROFILES = (
    "100% Loss", "3G", "DSL", "Edge", "High Latency DNS", "LTE", "Very Bad Network", "Wi-Fi", "Wi-Fi 802.11ac",
)
CONDITION_TYPES = ("network_condition", "low_power")
OFF_WORDS = ("off", "none", "")


def _settings(step: dict[str, Any]) -> dict[str, Any]:
    return {**step, "app": SETTINGS}


def _open_page(row: str, page_marker: dict[str, Any], parent: str | None = None) -> list[dict[str, Any]]:
    """Open Settings › [parent ›] row. Settings may reopen on the page it was left on, so each
    navigation step is optional and the last step waits for something only that page shows."""
    steps = [_settings({"type": "launch"})]
    for label in ([parent] if parent else []) + [row]:
        steps += [
            _settings({"type": "scroll_to", "label": label, "optional": True, "max_swipes": 8}),
            _settings({"type": "tap_label", "label": label, "optional": True}),
        ]
    steps.append(_settings({"type": "wait", **page_marker, "timeout": 6}))
    return steps


def network_value(action: dict[str, Any]) -> str:
    value = str(action.get("profile", action.get("value", ""))).strip()
    if value.lower() in OFF_WORDS:
        return "off"
    for profile in NETWORK_PROFILES:
        if profile.lower() == value.lower():
            return profile
    raise ValueError(
        f"network_condition profile '{value}' is not a Network Link Conditioner preset; use one of "
        f"{', '.join(NETWORK_PROFILES)} or off"
    )


def low_power_value(action: dict[str, Any]) -> bool:
    value = action.get("on", action.get("value"))
    if isinstance(value, bool):
        return value
    if str(value).lower() in ("on", "true", "1"):
        return True
    if str(value).lower() in ("off", "false", "0"):
        return False
    raise ValueError("low_power needs \"on\": true or false")


def network_steps(profile: str) -> list[dict[str, Any]]:
    steps = _open_page(
        "Network Link Conditioner", {"label": "Enable", "element_type": "Switch"}, parent="Developer",
    )
    if profile != "off":
        steps.append(_settings({"type": "tap_label", "label": profile, "element_type": "Cell"}))
    steps.append(_settings({"type": "set_switch", "label": "Enable", "element_type": "Switch", "on": profile != "off"}))
    return steps


def low_power_steps(on: bool) -> list[dict[str, Any]]:
    marker = {"label": "Low Power Mode", "element_type": "Switch"}
    return _open_page("Battery", marker) + [_settings({"type": "set_switch", **marker, "on": on})]


def expand(actions: list[dict[str, Any]], return_app: str | None) -> tuple[list[dict[str, Any]], list[int]]:
    """The actions with each condition step replaced by its Settings steps, then (when the app
    under test is known) an `activate` back to it; plus, per expanded step, the 1-based index of
    the step it came from, so a failure is reported against what the agent wrote."""
    expanded: list[dict[str, Any]] = []
    origin: list[int] = []
    for index, action in enumerate(actions, start=1):
        kind = action.get("type")
        if kind not in CONDITION_TYPES:
            expanded.append(action)
            origin.append(index)
            continue
        steps = network_steps(network_value(action)) if kind == "network_condition" else low_power_steps(low_power_value(action))
        back = action.get("return_to", return_app)
        if back:
            steps.append({"type": "activate", "app": back})
        expanded += [{**step, "via": kind} for step in steps]
        origin += [index] * len(steps)
    return expanded, origin


def requested(actions: list[dict[str, Any]]) -> dict[str, Any]:
    """What these actions leave switched on: {"network": "3G"} and/or {"low_power": True};
    a step that switches a condition off removes it."""
    state: dict[str, Any] = {}
    for action in actions:
        if action.get("type") == "network_condition":
            profile = network_value(action)
            state["network"] = None if profile == "off" else profile
        elif action.get("type") == "low_power":
            state["low_power"] = low_power_value(action) or None
    return state


def cleanup_steps(active: dict[str, Any], return_app: str | None = None) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if active.get("network"):
        actions.append({"type": "network_condition", "profile": "off"})
    if active.get("low_power"):
        actions.append({"type": "low_power", "on": False})
    return expand(actions, return_app)[0]


def state_path(cache_root: Path, udid: str) -> Path:
    return cache_root / f"conditions-{udid}.json"


def load(cache_root: Path, udid: str) -> dict[str, Any]:
    try:
        return json.loads(state_path(cache_root, udid).read_text())
    except (OSError, ValueError):
        return {}


def remember(cache_root: Path, udid: str, change: dict[str, Any]) -> dict[str, Any]:
    """Merge a change (None clears a key) into the iPhone's state file and return the result."""
    state = {**load(cache_root, udid), **change}
    state = {key: value for key, value in state.items() if value}
    path = state_path(cache_root, udid)
    if state:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state) + "\n")
    else:
        path.unlink(missing_ok=True)
    return state


def describe(state: dict[str, Any]) -> str:
    parts = [f"network={state['network']}"] if state.get("network") else []
    parts += ["low_power=on"] if state.get("low_power") else []
    return ",".join(parts)
