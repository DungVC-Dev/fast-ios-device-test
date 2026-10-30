#!/usr/bin/env python3

"""Screen map: what earlier runs saw of an app, so an agent writes the next flow right.

Both engines hand this module a trail of the tree reads and gestures their runs already made;
it merges them into ~/Library/Caches/fast-ui-map/<bundle id>.json. `fastUIMap` prints it.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

NOISE_LABEL = re.compile(r"^[\d:.,%\s]*$")
SCROLL_BAR_LABEL = re.compile(r"^(Vertical|Horizontal) scroll bar, \d+ pages?$")

KEPT_TYPES = frozenset({
    "Button", "Cell", "Switch", "RadioButton", "Tab", "Link", "TextField", "SecureTextField",
    "TextView", "Slider", "Heading", "StaticText",
})
INTERACTIVE = KEPT_TYPES - {"StaticText", "Heading"}
LABEL_LIMIT = 40
NODES_PER_SCREEN = 150
TITLE_BAND = 0.2
SCREEN_DAYS = 60
SCREENS_PER_APP = 400
SCROLL_GESTURES = ("swipe", "scroll_to")
ENTRY_GESTURES = ("launch", "activate")
GESTURE_KEYS = (
    "label", "label_contains", "id", "element_type", "target", "anchor", "x", "y", "direction", "from", "to", "url",
    "hold", "edge", "at", "scale", "radians", "value", "index", "key", "count", "button", "modifiers", "taps", "dy", "spread",
)


def node_types(node: dict[str, Any]) -> set[str]:
    """A trail node has one `type`; a stored node has one per engine in `types`."""
    if "types" in node:
        return set(node["types"].values())
    return {node["type"]} if node.get("type") else set()


def node_label(node: dict[str, Any]) -> str:
    return str(node.get("label") or node.get("label_contains") or "")


def normalize_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the nodes a flow can select, without values, noise or long text; interactive first."""
    interactive: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for node in nodes:
        # The device runner cuts long labels itself and sends them as `label_contains`.
        label = str(node.get("label") or node.get("label_contains") or "").strip()
        identifier = str(node.get("id") or "")
        kind = str(node.get("type") or "")
        if not identifier and kind not in KEPT_TYPES:
            continue
        if label and (NOISE_LABEL.match(label) or SCROLL_BAR_LABEL.match(label)):
            label = ""
        if len(label) > LABEL_LIMIT and kind == "StaticText" and not identifier:
            continue
        if not label and not identifier:
            continue
        kept: dict[str, Any] = {}
        if len(label) > LABEL_LIMIT or (node.get("label_contains") and not node.get("label")):
            kept["label_contains"] = label[:LABEL_LIMIT]
        elif label:
            kept["label"] = label
        kept["type"] = kind
        if identifier:
            kept["id"] = identifier
        key = (node_label(kept), identifier)
        if key in seen:
            continue
        seen.add(key)
        (interactive if kind in INTERACTIVE else other).append(kept)
    return (interactive + other)[:NODES_PER_SCREEN]


def simulator_screen(nodes: list[dict[str, Any]]) -> tuple[str, str, list[dict[str, Any]]]:
    """AXe nodes → (app display name, navigation title, on-screen nodes as label/type/id)."""
    root = next((node for node in nodes if node.get("type") == "Application"), None)
    app_label = str((root or {}).get("AXLabel") or "")
    try:
        frame = (root or {})["frame"]
        left, top = float(frame["x"]), float(frame["y"])
        right, bottom = left + float(frame["width"]), top + float(frame["height"])
    except (KeyError, TypeError, ValueError):
        return app_label, "", []
    title, title_y = "", None
    kept: list[dict[str, Any]] = []
    for node in nodes:
        if node is root:
            continue
        try:
            box = node["frame"]
            x, y = float(box["x"]), float(box["y"])
            width, height = float(box["width"]), float(box["height"])
        except (KeyError, TypeError, ValueError):
            continue
        centre_x, centre_y = x + width / 2, y + height / 2
        if width <= 0 or height <= 0 or not (left <= centre_x <= right and top <= centre_y <= bottom):
            continue
        label = str(node.get("AXLabel") or "").strip()
        kind = str(node.get("type") or "")
        if kind == "Heading" and label and y < top + (bottom - top) * TITLE_BAND and (title_y is None or y < title_y):
            title, title_y = label, y
        kept.append({"label": label, "type": kind, "id": str(node.get("AXUniqueId") or "")})
    return app_label, title, kept


def tokens(nodes: list[dict[str, Any]]) -> set[str]:
    """Identity of a screen: ids and interactive labels, types left out so engines agree."""
    found: set[str] = set()
    texts: set[str] = set()
    for node in nodes:
        if node.get("id"):
            found.add(f"id:{node['id']}")
        label = node_label(node)
        if not label:
            continue
        kinds = node_types(node)
        if kinds & INTERACTIVE:
            found.add(label)
        elif "StaticText" in kinds:
            texts.add(label)
    return found or texts


def jaccard(left: set[str], right: set[str]) -> float:
    shared = len(left & right)
    union = len(left) + len(right) - shared
    return shared / union if union else 0.0


def identity(nodes: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """A screen's tokens and the `id:` tokens among them."""
    found = tokens(nodes)
    return found, {token for token in found if token.startswith("id:")}


def similarity(title: str, observed: tuple[set[str], set[str]], stored_title: str,
               stored: tuple[set[str], set[str]]) -> float | None:
    """Score of one stored screen against an observation, or None when it cannot match."""
    if title and stored_title:
        if title != stored_title:
            return None
        left, right, needed = observed[0], stored[0], 0.3
    elif len(observed[1]) >= 3 and len(stored[1]) >= 3:
        left, right, needed = observed[1], stored[1], 0.5
    else:
        left, right, needed = observed[0], stored[0], 0.6
    # Jaccard is at most the ratio of the two sizes: skip the set work when that is too low.
    if not left or not right or min(len(left), len(right)) / max(len(left), len(right)) < needed:
        return None
    score = jaccard(left, right)
    return score if score >= needed else None


def match(screens: dict[str, dict[str, Any]], title: str, nodes: list[dict[str, Any]],
          cache: dict[str, tuple[set[str], set[str]]] | None = None) -> str | None:
    """Best stored screen for an observation; `cache` keeps each stored screen's tokens
    across the observations of one merge."""
    observed = identity(nodes)
    cache = {} if cache is None else cache
    best, best_score = None, -1.0
    for key, screen in screens.items():
        if key not in cache:
            cache[key] = identity(screen["nodes"])
        score = similarity(title, observed, screen.get("title", ""), cache[key])
        if score is not None and score > best_score:
            best, best_score = key, score
    return best


def kept_gesture(action: dict[str, Any]) -> dict[str, Any]:
    """What a step did, without typed text, launch arguments or timing."""
    kept = {"type": action.get("type")}
    kept.update({key: action[key] for key in GESTURE_KEYS if key in action})
    return kept


class Trail:
    """One Simulator run's tree reads and successful gestures, in the shape `record` takes.

    Only the latest read counts. A gesture starts from the read taken just before the last
    touch of its action (a `tap_nearest` reads again after its tap, a prompt tap comes before
    the real one); reads after that touch are where the gesture led.
    """

    def __init__(self, bundle_id: str) -> None:
        self.bundle_id = bundle_id
        self.app_label: str | None = None
        self.capture_label = True
        self.latest: list[dict[str, Any]] | None = None
        self.touched = False
        self.before: list[dict[str, Any]] | None = None
        self.entries: list[dict[str, Any]] = []

    def read(self, nodes: list[dict[str, Any]]) -> None:
        self.latest = nodes

    def start_action(self) -> None:
        self.touched, self.before = False, None

    def touch(self) -> None:
        self.touched, self.before, self.latest = True, self.latest, None

    def append(self, nodes: list[dict[str, Any]]) -> None:
        app_label, title, kept = simulator_screen(nodes)
        if self.capture_label:
            self.app_label, self.capture_label = app_label, False
        if app_label != self.app_label:
            entry: dict[str, Any] = {"break": True}
        else:
            entry = {"screen": {"app": self.bundle_id, "title": title, "nodes": kept}}
        if not self.entries or self.entries[-1] != entry:
            self.entries.append(entry)

    def gesture(self, action: dict[str, Any]) -> None:
        start = self.before if self.touched else self.latest
        if not self.touched:
            self.latest = None
        if start is not None:
            self.append(start)
        entry: dict[str, Any] = {"gesture": kept_gesture(action)}
        if start is None:
            entry["from"] = None
        self.entries.append(entry)
        self.touched, self.before = False, None
        if action.get("type") in ENTRY_GESTURES and action.get("app") in (None, self.bundle_id):
            self.capture_label = True

    def finish(self) -> list[dict[str, Any]]:
        if self.latest is not None:
            self.append(self.latest)
            self.latest = None
        return self.entries


def timestamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def new_map(app: str) -> dict[str, Any]:
    return {"version": 1, "app": app, "updated": "", "next_key": 1, "screens": {}, "edges": []}


def merge_nodes(screen: dict[str, Any], nodes: list[dict[str, Any]], engine: str) -> None:
    stored = {(node_label(node), node.get("id", "")): node for node in screen["nodes"]}
    for node in nodes:
        key = (node_label(node), node.get("id", ""))
        if key in stored:
            stored[key]["types"][engine] = node["type"]
        elif len(screen["nodes"]) < NODES_PER_SCREEN:
            kept = {name: value for name, value in node.items() if name != "type"}
            kept["types"] = {engine: node["type"]}
            screen["nodes"].append(kept)
            stored[key] = kept


def edge_key(origin: str, action: dict[str, Any]) -> tuple[str, str]:
    return origin, json.dumps(action, sort_keys=True)


def add_edge(map_: dict[str, Any], index: dict[tuple[str, str], dict[str, Any]], origin: str,
             action: dict[str, Any], target: str, now: datetime) -> None:
    """Count a way from `origin`; `index` maps (from, gesture) to the map's edge."""
    edge = index.get(edge_key(origin, action))
    if edge is not None:
        edge.update(to=target, last_seen=timestamp(now), count=edge["count"] + 1)
        return
    edge = {"from": origin, "gesture": action, "to": target, "last_seen": timestamp(now), "count": 1}
    map_["edges"].append(edge)
    index[edge_key(origin, action)] = edge


def merge_trail(maps: dict[str, dict[str, Any]], trail: list[dict[str, Any]], engine: str, now: datetime) -> None:
    """Fold one run's trail into the maps of the apps it touched; only apps in `maps` change."""
    previous: tuple[str, str] | None = None
    pending: tuple[tuple[str, str] | None, dict[str, Any]] | None = None
    entry_next = False
    caches: dict[str, dict[str, tuple[set[str], set[str]]]] = {app: {} for app in maps}
    edges = {app: {edge_key(edge["from"], edge["gesture"]): edge for edge in map_["edges"]} for app, map_ in maps.items()}
    for item in trail:
        if "break" in item:
            previous, pending = None, None
        elif "gesture" in item:
            action = kept_gesture(item["gesture"])
            pending = (previous if "from" not in item else None, action)
            entry_next = action.get("type") in ENTRY_GESTURES
        elif "screen" in item:
            observed = item["screen"]
            app, title = observed.get("app", ""), str(observed.get("title") or "")[:LABEL_LIMIT]
            nodes = normalize_nodes(observed.get("nodes", []))
            if not tokens(nodes) or app not in maps:
                previous, pending = None, None
                continue
            map_ = maps[app]
            origin = pending[0] if pending and pending[0] and pending[0][0] == app else None
            action = pending[1] if pending else None
            if (origin and action and action.get("type") in SCROLL_GESTURES
                    and map_["screens"][origin[1]].get("title", "") == title):
                key = origin[1]
            else:
                key = match(map_["screens"], title, nodes, caches[app])
            if key is None:
                key = f"s{map_['next_key']}"
                map_["next_key"] += 1
                map_["screens"][key] = {"title": title, "first_seen": timestamp(now), "seen": 0, "nodes": []}
            screen = map_["screens"][key]
            merge_nodes(screen, nodes, engine)
            caches[app].pop(key, None)
            screen["title"] = screen.get("title") or title
            screen["last_seen"] = timestamp(now)
            screen["seen"] += 1
            if entry_next:
                screen["entry"] = True
            if origin and action and origin[1] != key:
                add_edge(map_, edges[app], origin[1], action, key, now)
            previous, pending, entry_next = (app, key), None, False


def prune(map_: dict[str, Any], now: datetime) -> None:
    """Drop screens unseen for 60 days, then the least recently seen beyond 400, with their edges."""
    cutoff = now - timedelta(days=SCREEN_DAYS)
    screens = {key: screen for key, screen in map_["screens"].items() if parse_time(screen["last_seen"]) >= cutoff}
    if len(screens) > SCREENS_PER_APP:
        recent = sorted(screens, key=lambda key: screens[key]["last_seen"], reverse=True)[:SCREENS_PER_APP]
        screens = {key: screens[key] for key in screens if key in recent}
    map_["screens"] = screens
    map_["edges"] = [edge for edge in map_["edges"] if edge["from"] in screens and edge["to"] in screens]


def map_dir() -> Path:
    return Path(os.environ.get("FAST_UI_MAP_DIR") or Path.home() / "Library/Caches/fast-ui-map").expanduser()


def map_path(app: str) -> Path:
    return map_dir() / f"{re.sub(r'[^A-Za-z0-9._-]', '_', app)}.json"


def parse_map(path: Path) -> dict[str, Any] | None:
    """The map in `path`, or None when it is not one this version wrote."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(loaded, dict) or not all(key in loaded for key in new_map("")):
        return None
    if not isinstance(loaded["screens"], dict) or not isinstance(loaded["edges"], list):
        return None
    return loaded


def load_map(path: Path, app: str) -> dict[str, Any]:
    """For `record`, under the lock: a map that does not parse is kept aside as `.bad`."""
    if not path.exists():
        return new_map(app)
    loaded = parse_map(path)
    if loaded is None:
        path.replace(path.with_name(path.name + ".bad"))
        return new_map(app)
    return loaded


def record(trail: list[dict[str, Any]], engine: str, now: datetime | None = None) -> None:
    """Merge a trail into each app's map, one app at a time under that map's lock."""
    if os.environ.get("FAST_UI_MAP") == "0" or not trail:
        return
    now = now or datetime.now(timezone.utc)
    apps = sorted({item["screen"].get("app", "") for item in trail if "screen" in item} - {""})
    for app in apps:
        path = map_path(app)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path.with_name(path.name + ".lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            map_ = load_map(path, app)
            merge_trail({app: map_}, trail, engine, now)
            prune(map_, now)
            map_["updated"] = timestamp(now)
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_text(json.dumps(map_, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
            os.replace(temporary, path)


PATH_LIMIT = 6
# Labels and ids most pushed screens show, useless as proof of having arrived somewhere.
SCREEN_CHROME = {"backbutton", "back", "chevron", "close", "cancel", "done", "edit", "more", "search"}
INDEX_LABELS = 8


def file_link(path: Path | str) -> str:
    """Absolute `file://` URL: terminals open it on click, a bare or relative path they do not."""
    return Path(path).expanduser().resolve().as_uri()


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def shortest_routes(map_: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The edges from an entry screen to every reachable screen, breadth first, at most 6."""
    routes: dict[str, list[dict[str, Any]]] = {key: [] for key, screen in map_["screens"].items() if screen.get("entry")}
    frontier = list(routes)
    while frontier:
        following = []
        for origin in frontier:
            if len(routes[origin]) >= PATH_LIMIT:
                continue
            for edge in map_["edges"]:
                if edge["from"] == origin and edge["to"] not in routes:
                    routes[edge["to"]] = routes[origin] + [edge]
                    following.append(edge["to"])
        frontier = following
    return routes


def shortest_paths(map_: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Gestures from an entry screen to every reachable screen."""
    return {key: [edge["gesture"] for edge in route] for key, route in shortest_routes(map_).items()}


def screen_name(screens: dict[str, Any], key: str) -> str:
    screen = screens[key]
    first = next((node.get("id") for node in screen["nodes"] if node.get("id")), None)
    labels = [node_label(node) for node in screen["nodes"] if node_label(node) and node_types(node) & INTERACTIVE]
    return f'{key} "{screen.get("title") or first or (labels[0] if labels else key)}"'


def node_selector(node: dict[str, Any]) -> dict[str, Any]:
    key = "id" if node.get("id") else "label" if node.get("label") else "label_contains"
    return {key: node[key]}


def expect_for(target: dict[str, Any], before: dict[str, Any]) -> dict[str, Any] | None:
    """A selector the target screen shows and the screen before it does not, so the guard
    cannot pass before the step has moved (Settings has a "General" row; General's title is no
    proof of arriving there)."""
    seen = {before.get("title") or ""} | {node_label(node) for node in before["nodes"]} | {
        str(node.get("id")) for node in before["nodes"] if node.get("id")}
    seen |= {value.lower() for value in seen}

    def label_of(node: dict[str, Any]) -> dict[str, Any]:
        return node_selector({key: value for key, value in node.items() if key != "id"})

    # The title, then a row or button only this screen has, then an id, then any text; never
    # the chrome every pushed screen shows (a back button proves nothing).
    candidates = ([{"label": target["title"]}] if target.get("title") else []) + [
        label_of(node) for node in target["nodes"] if node_label(node) and node_types(node) & INTERACTIVE] + [
        {"id": node["id"]} for node in target["nodes"] if node.get("id")] + [
        label_of(node) for node in target["nodes"] if node_label(node)]
    usable = [candidate for candidate in candidates if (value := str(next(iter(candidate.values())))) not in seen
              and value.lower() not in seen and value.lower() not in SCREEN_CHROME]
    # Text without digits first: a version, a count or a date differs on the next iPhone.
    return next((candidate for candidate in usable if not any(ch.isdigit() for ch in str(next(iter(candidate.values()))))),
                usable[0] if usable else None)


def path_to(app: str, stored: dict[str, Any], text: str) -> int:
    """`--path-to`: a guarded request from an entry screen to the screen that has `text` as
    its title (else a node), ready for `do`."""
    screens, needle = stored["screens"], text.lower()
    by_title = [key for key, screen in screens.items() if needle in str(screen.get("title") or "").lower()]
    by_node = [(key, node) for key, screen in screens.items() for node in screen["nodes"]
               if needle in node_label(node).lower() or needle in str(node.get("id", "")).lower()]
    candidates = by_title or [key for key, _ in by_node]
    if not candidates:
        print(f"PATH none text={text}")
        return 0
    routes = shortest_routes(stored)
    reachable = sorted((key for key in candidates if key in routes),
                       key=lambda key: (len(routes[key]), -parse_time(screens[key]["last_seen"]).timestamp()))
    if not reachable:
        print(f"PATH none text={text} seen={screen_name(screens, candidates[0])} (no recorded way there)")
        return 0
    key = reachable[0]
    route = routes[key]
    start = route[0]["from"] if route else key
    select = "" if by_title else f" select={compact(node_selector(next(node for k, node in by_node if k == key)))}"
    request = []
    for edge in route:
        step = dict(edge["gesture"])
        expected = expect_for(screens[edge["to"]], screens[edge["from"]])
        if expected:
            step["expect"] = expected
        request.append(step)
    print(f"PATH app={app} to={screen_name(screens, key)} from={screen_name(screens, start)} steps={len(route)}{select}")
    print(compact(request))
    return 0


def path_text(paths: dict[str, list[dict[str, Any]]], key: str) -> str:
    if key not in paths:
        return "unknown"
    return compact(paths[key]) if paths[key] else "entry"


def types_text(node: dict[str, Any]) -> str:
    return ",".join(f"{engine}:{kind}" for engine, kind in node["types"].items())


def list_maps() -> int:
    maps = sorted(map_dir().glob("*.json")) if map_dir().is_dir() else []
    if not maps:
        print(f"MAP none dir={file_link(map_dir())}")
    for path in maps:
        stored = parse_map(path)
        if stored is None:
            print(f"MAP bad app={path.stem} path={file_link(path)}")
            continue
        print(f"MAP app={stored['app']} screens={len(stored['screens'])} size={max(1, round(path.stat().st_size / 1024))}K "
              f"updated={stored['updated'][:10]} path={file_link(path)}")
    return 0


def show_map(app: str, find: str | None, screen_key: str | None, path_text_to: str | None = None) -> int:
    path = map_path(app)
    if not path.exists():
        print(f"MAP none app={app}")
        return 0
    stored = parse_map(path)
    if stored is None:
        print(f"MAP bad app={app} path={file_link(path)}")
        return 1
    if path_text_to is not None:
        return path_to(app, stored, path_text_to)
    paths = shortest_paths(stored)
    screens = stored["screens"]

    def name(key: str) -> str:
        return screen_name(screens, key)

    if screen_key:
        if screen_key not in screens:
            print(f"SCREEN none key={screen_key} app={app}")
            return 1
        screen = screens[screen_key]
        print(f"SCREEN {name(screen_key)} seen={screen['seen']} last={screen['last_seen'][:10]} "
              f"path={path_text(paths, screen_key)}")
        for node in screen["nodes"]:
            label = f"label={node['label']} " if node.get("label") else (
                f"label_contains={node['label_contains']} " if node.get("label_contains") else "")
            identifier = f"id={node['id']} " if node.get("id") else ""
            print(f"{label}{identifier}types={types_text(node)}")
        return 0
    if find is not None:
        needle, found = find.lower(), 0
        for key, screen in screens.items():
            for node in screen["nodes"]:
                if needle in node_label(node).lower() or needle in str(node.get("id", "")).lower():
                    select_key = "id" if node.get("id") else "label" if node.get("label") else "label_contains"
                    print(f"{name(key)} select={compact({select_key: node[select_key]})} types={types_text(node)} "
                          f"path={path_text(paths, key)}")
                    found += 1
        if not found:
            print(f"FIND none text={find}")
        return 0
    print(f"MAP app={app} screens={len(screens)} edges={len(stored['edges'])} updated={stored['updated'][:10]} "
          f"path={file_link(path)}")
    for key, screen in screens.items():
        labels = [node_label(node) for node in screen["nodes"] if node_label(node) and node_types(node) & INTERACTIVE]
        print(f"{name(key)} seen={screen['seen']} last={screen['last_seen'][:10]} labels={compact(labels[:INDEX_LABELS])} "
              f"path={path_text(paths, key)}")
    return 0


def clear_map(path: Path) -> None:
    """Delete one map and its `.bad` copy under the map's lock. The lock file stays: a run
    holding it would otherwise write while the next run locks a new file."""
    with open(path.with_name(path.name + ".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".bad").unlink(missing_ok=True)


def clear(target: str) -> int:
    directory = map_dir()
    if target == "--all":
        apps = sorted(directory.glob("*.json")) if directory.is_dir() else []
        for path in apps:
            clear_map(path)
        for bad in directory.glob("*.json.bad") if directory.is_dir() else []:
            bad.unlink(missing_ok=True)
        print(f"CLEARED apps={len(apps)}")
        return 0
    path = map_path(target)
    if path.parent.is_dir():
        clear_map(path)
    print(f"CLEARED app={target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments[:1] == ["clear"]:
        if len(arguments) != 2:
            print("usage: fastUIMap clear <bundle id> | --all", file=sys.stderr)
            return 2
        return clear(arguments[1])
    parser = argparse.ArgumentParser(
        prog="fastUIMap",
        description="Print what earlier fastSimulatorTest / fastDeviceTest runs saw of an app "
        "(~/Library/Caches/fast-ui-map). `fastUIMap clear <bundle id>|--all` deletes maps.",
    )
    parser.add_argument("app", nargs="?", help="Bundle id; without it, list every map")
    parser.add_argument("--find", help="Nodes whose label or id contains this text, with a selector and the path")
    parser.add_argument("--screen", help="Every node of one screen key (s12)")
    parser.add_argument("--path-to", help="A guarded do request (each step with an expect) from an entry screen to "
                        "the screen titled with this text, else the one showing it")
    args = parser.parse_args(arguments)
    if not args.app:
        return list_maps()
    return show_map(args.app, args.find, args.screen, args.path_to)


if __name__ == "__main__":
    raise SystemExit(main())
