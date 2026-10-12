# fast-ios-device-test 1.2.0 — kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nâng tool từ 1.1.0 lên 1.2.0: FAIL tự giải thích, dump gọn, selector `id`/`value`, cache hierarchy, settle opt-in, thêm action simulator, tắt wait-for-idle trên iPhone, review nhanh hơn, tài liệu gọn, cài đặt không cần Homebrew.

**Architecture:** Engine simulator (`scripts/fast_ui.py`) và runner iPhone (`device-runner/UITests/FlowRunner.swift`) vẫn feature-agnostic, chỉ đọc flow JSON; mọi thay đổi là thêm selector, thêm action, thêm chẩn đoán và cache trong engine. Tài liệu và installer đổi theo. Không thêm cấu hình theo dự án.

**Tech Stack:** Python 3.9 (`/usr/bin/python3` của Xcode), `unittest` + `unittest.mock`, AXe 1.8.0, `xcrun simctl`, XCUITest (Swift 5, iOS 17+), bash.

**Spec:** `docs/optimization-research-2026-10-12.md` (mục 3, 4, 8, 10, 12, 13, 14, 15).

## Global Constraints

- Python 3.9: không dùng `match`, không dùng `X | Y` ngoài annotation, không `zip(strict=)`, không `str.removesuffix` ngoài 3.9.
- Mỗi thay đổi trong `scripts/*.py` đi kèm test trong `scripts/test_fast_ui.py` hoặc `scripts/test_fast_ui_review.py`; chạy bằng `cd scripts && python3 -m unittest test_fast_ui test_fast_ui_review`.
- Dòng PASS/FAIL giữ nguyên các trường hiện có (`task=`, `step=`, `total=`, `build=`, `error=`, `artifacts=`); chỉ được thêm trường mới ở cuối.
- Flow version vẫn là `1`; mọi khoá mới là tuỳ chọn, flow cũ chạy y nguyên.
- Engine không được chứa tên màn hình, label hay bundle id của dự án nào.
- Mặc định không đổi hành vi thời gian: `settle` tắt, `wait_for_idle` bật, cache hierarchy chỉ dùng ở lần poll đầu của một action tap.
- Commit message không có dòng attribution của Claude.
- Mọi file nằm trong `~/Resources/Tool/fast-ios-device-test`.

## Review Focus

1. Hai node `StaticText` cùng label, không có Button → `tap_label` không được fallback, phải FAIL kèm gợi ý (test ở Task 4 (A4)).
2. Node từ `describe-ui` không có `frame` → `compact_node` không crash, không có khoá `frame`/`center` (test ở Task 1 (A1)).
3. Tap xong rồi `wait` màn hình kế trong vòng 300 ms → không được đọc cache cũ (test ở Task 5 (A5)).
4. `settle: true` trên màn hình không bao giờ đứng yên → trả về sau timeout, flow không FAIL (test ở Task 6 (A6)).
5. Tên iPhone khớp hai máy ("iPhone 16" khớp "iPhone 16 - 26.2" và "iPhone 16 blue") → lỗi liệt kê cả hai, không tự chọn (test ở Task 10 (B1)).

---

## Task 0: Backup và git

**Files:**
- Create: `.gitignore`
- Create (ngoài gói): `~/Resources/Tool/fast-ios-device-test-1.1.0-backup.zip`

- [ ] **Step 1: Zip bản đang chạy**

Run:
```bash
cd ~/Resources/Tool && zip -rq fast-ios-device-test-1.1.0-backup.zip fast-ios-device-test -x '*.DS_Store' -x '*__pycache__*'
ls -la fast-ios-device-test-1.1.0-backup.zip
```
Expected: file ~130 KB tồn tại.

- [ ] **Step 2: Tạo `.gitignore`** với nội dung đúng ba dòng: `__pycache__/`, `.DS_Store`, `build/`.

- [ ] **Step 3: git init và commit gốc**

Run:
```bash
cd ~/Resources/Tool/fast-ios-device-test && git init -q && git add -A && git commit -qm "1.1.0 as installed on 2026-10-02 with Xcode 27 fixes" && git log --oneline
```
Expected: một commit.

- [ ] **Step 4: Xác nhận test nền**

Run: `cd scripts && python3 -m unittest test_fast_ui test_fast_ui_review`
Expected: `Ran 63 tests ... OK` (53 + 10).

---

## Phase A — Engine simulator (`scripts/fast_ui.py`)

### Task 1 (A1): `flatten` chỉ trả node thật, dump gọn

**Files:**
- Modify: `scripts/fast_ui.py:113-120` (`flatten`), `:742-747` (`dump`), `:1019-1024` (failure-ui)
- Test: `scripts/test_fast_ui.py` (class `HierarchyTests`)

**Interfaces:**
- Produces: `flatten(value) -> Iterator[dict]` chỉ yield dict là node (có khoá `type` hoặc `AXLabel` hoặc `children`) và chỉ đệ quy vào `children`.
- Produces: `compact_node(node: dict) -> dict` trả về các khoá có giá trị trong `label`, `type`, `id` (từ `AXUniqueId`), `value` (từ `AXValue`), `frame` (`x`, `y`, `width`, `height` làm tròn 1 chữ số), `center` (`[cx, cy]`); không bao giờ có `children`.
- Produces: `write_dump(path: Path, nodes: list[dict]) -> None` ghi `json.dumps([compact_node(n) ...], indent=1, ensure_ascii=False)`.

- [ ] **Step 1: Viết test fail**

```python
def test_flatten_skips_frame_dicts_and_recurses_children_only(self) -> None:
    tree = [{"type": "Application", "frame": {"x": 0, "y": 0, "width": 10, "height": 10},
             "children": [{"type": "Button", "AXLabel": "Go", "frame": {"x": 1, "y": 2, "width": 4, "height": 4}}]}]
    nodes = list(fast_ui.flatten(tree))
    self.assertEqual([n.get("type") for n in nodes], ["Application", "Button"])

def test_compact_node_drops_children_and_survives_missing_frame(self) -> None:
    node = {"type": "Button", "AXLabel": "Go", "AXUniqueId": "go", "AXValue": "1",
            "frame": {"x": 1, "y": 2, "width": 4, "height": 4}, "children": [{"type": "Image"}]}
    self.assertEqual(fast_ui.compact_node(node),
                     {"label": "Go", "type": "Button", "id": "go", "value": "1",
                      "frame": {"x": 1, "y": 2, "width": 4, "height": 4}, "center": [3.0, 4.0]})
    self.assertEqual(fast_ui.compact_node({"type": "Other"}), {"type": "Other"})

def test_dump_file_is_flat_and_compact(self) -> None:
    nodes = [{"AXLabel": "Widgets", "type": "Button", "frame": {"x": 0, "y": 0, "width": 1, "height": 1},
              "children": [{"type": "Image", "frame": {"x": 0, "y": 0, "width": 1, "height": 1}}]}]
    with tempfile.TemporaryDirectory() as raw, mock.patch.object(fast_ui, "hierarchy", return_value=nodes), \
            mock.patch.object(fast_ui.time, "sleep"):
        fast_ui.execute_action({"type": "dump", "name": "home"}, "SIM", Path(raw), 3, [])
        text = (Path(raw) / "home-ui.json").read_text()
    self.assertNotIn("children", text)
    self.assertIn('"center"', text)
```

- [ ] **Step 2: Chạy để thấy fail**

Run: `cd scripts && python3 -m unittest test_fast_ui.HierarchyTests -v`
Expected: 3 FAIL/ERROR (`compact_node` chưa có; `flatten` trả 3 phần tử vì có dict `frame`).

- [ ] **Step 3: Sửa `flatten`, thêm `compact_node`, `write_dump`; dùng `write_dump` ở action `dump` và ở `failure-ui.json`**

`flatten` giữ nguyên chữ ký, đổi thân: yield `value` khi là dict có một trong ba khoá, rồi `yield from flatten(value.get("children") or [])`; với list thì duyệt từng phần tử.

- [ ] **Step 4: Chạy toàn bộ test**

Run: `cd scripts && python3 -m unittest test_fast_ui test_fast_ui_review`
Expected: OK (test `test_dump_action_writes_labels_and_hierarchy` cũ vẫn pass).

- [ ] **Step 5: Commit** `git commit -am "engine: flat compact dumps, flatten yields real nodes only"`

---

### Task 2 (A2): Selector `id`, `value`; `tap_label` nhận mọi khoá selector

**Files:**
- Modify: `scripts/fast_ui.py:162-189` (`matches`), `:725-737` (`tap_label`)
- Test: `scripts/test_fast_ui.py` (class `ActionTests`)

**Interfaces:**
- Produces: `SELECTOR_KEYS = ("label", "label_contains", "label_is_empty", "id", "value", "element_type", "frame")`.
- Produces: `matches(node, selector)` hiểu thêm `id` (so với `node["AXUniqueId"]`) và `value` (so với `str(node.get("AXValue"))`).
- Produces: `selector_of(action: dict, default_type: str | None = None) -> dict` lấy các khoá trong `SELECTOR_KEYS` có mặt trong action; nếu thiếu `element_type` và `default_type` khác None thì đặt `element_type = default_type`.
- `tap_label` dùng `selector_of(action, "Button")`; yêu cầu ít nhất một trong `label`, `label_contains`, `id`; lỗi `missing 'label' or 'id' in action N` nếu không có.

- [ ] **Step 1: Viết test fail**

```python
def test_matches_id_and_value(self) -> None:
    node = {"AXLabel": "Wi-Fi", "AXUniqueId": "wifiSwitch", "AXValue": "1", "type": "Switch", "frame": {}}
    self.assertTrue(fast_ui.matches(node, {"id": "wifiSwitch"}))
    self.assertTrue(fast_ui.matches(node, {"value": "1", "element_type": "Switch"}))
    self.assertFalse(fast_ui.matches(node, {"id": "other"}))

def test_tap_label_accepts_id_and_label_contains(self) -> None:
    node = {"AXLabel": "Continue to app", "AXUniqueId": "cta", "type": "Button",
            "frame": {"x": 0, "y": 0, "width": 10, "height": 10}}
    with mock.patch.object(fast_ui, "hierarchy", return_value=[node]), \
            mock.patch.object(fast_ui, "tap_point") as tap:
        fast_ui.execute_action({"type": "tap_label", "id": "cta"}, "SIM", Path("/tmp"), 1, [])
        fast_ui.execute_action({"type": "tap_label", "label_contains": "Continue"}, "SIM", Path("/tmp"), 2, [])
    self.assertEqual(tap.call_count, 2)
    with self.assertRaisesRegex(fast_ui.FastUIError, "missing 'label' or 'id'"):
        fast_ui.execute_action({"type": "tap_label"}, "SIM", Path("/tmp"), 3, [])
```

- [ ] **Step 2: Chạy để thấy fail** — `python3 -m unittest test_fast_ui.ActionTests -v`, Expected: 2 FAIL.
- [ ] **Step 3: Thêm `SELECTOR_KEYS`, `selector_of`, mở rộng `matches`, sửa nhánh `tap_label`.**
- [ ] **Step 4: Chạy toàn bộ test** — Expected OK.
- [ ] **Step 5: Commit** `git commit -am "engine: id/value selectors, tap_label takes any selector key"`

---

### Task 3 (A3): FAIL in type và gợi ý label gần giống

**Files:**
- Modify: `scripts/fast_ui.py:35-36` (`FastUIError`), `:144-155` (`visible_labels`), `:192-232` (`wait_nodes`, `wait_selector`)
- Test: `scripts/test_fast_ui.py` (class `ActionTests`)

**Interfaces:**
- Produces: `class FastUIError(RuntimeError)` có thuộc tính `nodes: list[dict]` (mặc định `[]`), `wait_nodes` gán `error.nodes = nodes` trước khi raise.
- Produces: `typed_labels(nodes: list[dict], limit: int = 25) -> list[str]` trả về `"<label> (<type>)"` theo thứ tự màn hình, cùng lọc nhiễu như `visible_labels`; type thiếu thì chỉ `"<label>"`.
- Produces: `selector_hints(selector: dict, nodes: list[dict]) -> str`:
  - nếu có node `AXLabel == selector["label"]` nhưng type khác `selector["element_type"]` → `"; 'X' exists as StaticText, not Button: add element_type or use tap_first"`;
  - nếu không, với `label`/`label_contains` → `difflib.get_close_matches(wanted, labels, n=3, cutoff=0.6)` cộng các label chứa `wanted` không phân biệt hoa thường → `"; closest labels: [A, B]"`; không có gì thì chuỗi rỗng.
- Thông điệp timeout của `wait_nodes` đổi thành `timed out waiting for UI selector; visible labels: [<typed_labels>]`; `wait_selector` bắt lỗi và raise lại với `selector_hints` nối vào cuối.

- [ ] **Step 1: Viết test fail**

```python
def test_wait_timeout_lists_types_and_explains_type_mismatch(self) -> None:
    nodes = [{"AXLabel": "Add Widget", "type": "StaticText", "frame": {"x": 0, "y": 10}}]
    with mock.patch.object(fast_ui, "hierarchy", return_value=nodes), mock.patch.object(fast_ui.time, "sleep"):
        with self.assertRaises(fast_ui.FastUIError) as caught:
            fast_ui.wait_selector("SIM", {"label": "Add Widget", "element_type": "Button"}, 0.01, [])
    self.assertIn("Add Widget (StaticText)", str(caught.exception))
    self.assertIn("exists as StaticText, not Button", str(caught.exception))

def test_wait_timeout_suggests_close_labels(self) -> None:
    nodes = [{"AXLabel": "Widget Gallery", "type": "StaticText", "frame": {"x": 0, "y": 10}}]
    with mock.patch.object(fast_ui, "hierarchy", return_value=nodes), mock.patch.object(fast_ui.time, "sleep"):
        with self.assertRaises(fast_ui.FastUIError) as caught:
            fast_ui.wait_selector("SIM", {"label": "Widget gallery"}, 0.01, [])
    self.assertIn("closest labels: [Widget Gallery]", str(caught.exception))
```

- [ ] **Step 2: Chạy để thấy fail** — Expected: 2 FAIL.
- [ ] **Step 3: Thêm `nodes` vào `FastUIError`, viết `typed_labels`, `selector_hints`, nối vào `wait_selector`.**
- [ ] **Step 4: Chạy toàn bộ test** — Expected OK (`test_wait_timeout_error_lists_visible_labels` vẫn pass vì label vẫn xuất hiện).
- [ ] **Step 5: Commit** `git commit -am "engine: FAIL lists element types and suggests close labels"`

---

### Task 4 (A4): `tap_label` fallback sang node duy nhất cùng label

**Files:**
- Modify: `scripts/fast_ui.py` nhánh `tap_label` trong `execute_action`
- Test: `scripts/test_fast_ui.py` (class `ActionTests`)

**Interfaces:**
- Produces: `resolve_tap_target(nodes: list[dict], selector: dict, explicit_type: bool) -> dict | None`: trả node Button khớp (sort `y`, `x`, lấy đầu); nếu không có và `explicit_type` là False → các node khớp selector bỏ `element_type`, có `frame` đủ 4 khoá; đúng một node thì trả node đó, khác thì `None`.
- `tap_label` dùng predicate `lambda nodes: resolve_tap_target(...) is not None` trong `wait_nodes`; khi tap node không phải Button, trả `{"fallback_type": "<type>"}` để vào `results`.

- [ ] **Step 1: Viết test fail**

```python
def test_tap_label_falls_back_to_the_only_node_with_that_label(self) -> None:
    node = {"AXLabel": "Add Widget", "type": "StaticText", "frame": {"x": 0, "y": 0, "width": 10, "height": 10}}
    with mock.patch.object(fast_ui, "hierarchy", return_value=[node]), mock.patch.object(fast_ui, "tap_point") as tap:
        result = fast_ui.execute_action({"type": "tap_label", "label": "Add Widget"}, "SIM", Path("/tmp"), 1, [])
    tap.assert_called_once_with("SIM", 5.0, 5.0, 0.15)
    self.assertEqual(result, {"fallback_type": "StaticText"})

def test_tap_label_does_not_fall_back_when_ambiguous_or_type_explicit(self) -> None:
    a = {"AXLabel": "Add", "type": "StaticText", "frame": {"x": 0, "y": 0, "width": 10, "height": 10}}
    b = {"AXLabel": "Add", "type": "Image", "frame": {"x": 0, "y": 20, "width": 10, "height": 10}}
    with mock.patch.object(fast_ui, "hierarchy", return_value=[a, b]), mock.patch.object(fast_ui.time, "sleep"), \
            mock.patch.object(fast_ui, "tap_point") as tap:
        with self.assertRaises(fast_ui.FastUIError):
            fast_ui.execute_action({"type": "tap_label", "label": "Add", "timeout": 0.01}, "SIM", Path("/tmp"), 1, [])
        with self.assertRaises(fast_ui.FastUIError):
            fast_ui.execute_action({"type": "tap_label", "label": "Add Widget", "element_type": "Button", "timeout": 0.01},
                                   "SIM", Path("/tmp"), 2, [])
    tap.assert_not_called()
```

- [ ] **Step 2: Chạy để thấy fail** — Expected: 2 FAIL.
- [ ] **Step 3: Viết `resolve_tap_target`, dùng trong nhánh `tap_label` (cả nhánh `optional`).**
- [ ] **Step 4: Chạy toàn bộ test** — Expected OK.
- [ ] **Step 5: Commit** `git commit -am "engine: tap_label falls back to a unique non-Button node"`

---

### Task 5 (A5): Cache hierarchy 300 ms

**Files:**
- Modify: `scripts/fast_ui.py:126-137` (`hierarchy`), `:302-337` (`swipe`, `tap_point`), `:394-403` (`step_labels`), `execute_action`
- Test: `scripts/test_fast_ui.py` (class `HierarchyTests`)

**Interfaces:**
- Produces: `HIERARCHY_REUSE = 0.3`; `hierarchy(udid: str, max_age: float = 0.0) -> list[dict]` trả bản cache nếu tuổi ≤ `max_age`, nếu không gọi AXe và ghi cache `(time.perf_counter(), nodes)` theo `udid`.
- Produces: `invalidate_hierarchy(udid: str) -> None`; gọi trong `tap_point`, `swipe`, và các action `launch`/`terminate`/`open_url`/`type_text` của Task 7 (A7).
- `wait_nodes(..., first_poll_max_age: float = 0.0)`: poll đầu dùng `hierarchy(udid, first_poll_max_age)`, các poll sau `max_age=0`. Nhánh `tap_label`, `tap_first`, `tap_nearest` truyền `HIERARCHY_REUSE`; `step_labels` gọi `hierarchy(udid, HIERARCHY_REUSE)`.

- [ ] **Step 1: Viết test fail**

```python
def test_hierarchy_reuses_a_fresh_tree_until_a_gesture(self) -> None:
    good = mock.Mock(stdout='[{"AXLabel": "A", "type": "Button"}]', returncode=0)
    with mock.patch.object(fast_ui, "axe", return_value=good) as axe, mock.patch.object(fast_ui.time, "sleep"):
        fast_ui.hierarchy("SIM")
        fast_ui.hierarchy("SIM", max_age=fast_ui.HIERARCHY_REUSE)
        self.assertEqual(axe.call_count, 1)
        fast_ui.tap_point("SIM", 1, 1, 0)
        fast_ui.hierarchy("SIM", max_age=fast_ui.HIERARCHY_REUSE)
        fast_ui.hierarchy("SIM")
    self.assertEqual(axe.call_count, 4)  # describe, tap, describe, describe
```

- [ ] **Step 2: Chạy để thấy fail** — Expected: TypeError (`max_age` chưa có).
- [ ] **Step 3: Thêm cache module-level, `invalidate_hierarchy`, tham số `max_age`, `first_poll_max_age`.**
- [ ] **Step 4: Chạy toàn bộ test** — Expected OK (`test_step_labels_poll_hierarchy_once` vẫn `assert_called_once`).
- [ ] **Step 5: Commit** `git commit -am "engine: reuse a <300ms hierarchy for the first poll of a tap"`

---

### Task 6 (A6): `settle` opt-in sau action

**Files:**
- Modify: `scripts/fast_ui.py` (`execute_action`, hàm mới)
- Test: `scripts/test_fast_ui.py` (class `ActionTests`)

**Interfaces:**
- Produces: `tree_signature(nodes: list[dict]) -> str` = sha1 của `"|".join(f"{label}/{type}/{x:.0f},{y:.0f},{w:.0f},{h:.0f}")` theo thứ tự `sort_nodes(nodes, ["y", "x"])`.
- Produces: `wait_settled(udid: str, timeout: float = 2.5, interval: float = 0.1, stable_for: float = 0.1) -> bool`: poll tới khi hai chữ ký liên tiếp bằng nhau và đã giữ ≥ `stable_for`; hết `timeout` trả `False`, không raise.
- Action `tap_label`, `tap_first`, `tap_nearest`, `tap_point`, `swipe`, `scroll_to` đọc `action.get("settle")`: `true` → `wait_settled(udid)`; số → `wait_settled(udid, timeout=số)`. Kết quả `{"settled": bool}` được gộp vào result của action (nếu action đã trả dict thì cập nhật, nếu `None` thì trả dict mới).
- `setup.settle_after_actions: true` bật mặc định cho mọi action tap/swipe của flow đó (đọc trong `main`, truyền qua tham số mới `defaults: dict` của `execute_action`, mặc định `{}`).

- [ ] **Step 1: Viết test fail**

```python
def test_wait_settled_returns_true_when_two_polls_match(self) -> None:
    a = [{"AXLabel": "A", "type": "Button", "frame": {"x": 0, "y": 0, "width": 1, "height": 1}}]
    b = [{"AXLabel": "A", "type": "Button", "frame": {"x": 0, "y": 5, "width": 1, "height": 1}}]
    with mock.patch.object(fast_ui, "hierarchy", side_effect=[a, b, b, b]), mock.patch.object(fast_ui.time, "sleep"):
        self.assertTrue(fast_ui.wait_settled("SIM", timeout=5, stable_for=0))

def test_wait_settled_gives_up_quietly_on_a_moving_screen(self) -> None:
    frames = iter(range(1000))
    moving = lambda udid, max_age=0.0: [{"AXLabel": "A", "type": "Image", "frame": {"x": 0, "y": next(frames), "width": 1, "height": 1}}]
    with mock.patch.object(fast_ui, "hierarchy", side_effect=moving), mock.patch.object(fast_ui.time, "sleep"):
        self.assertFalse(fast_ui.wait_settled("SIM", timeout=0.01))

def test_settle_flag_on_tap_records_result(self) -> None:
    node = {"AXLabel": "Go", "type": "Button", "frame": {"x": 0, "y": 0, "width": 2, "height": 2}}
    with mock.patch.object(fast_ui, "hierarchy", return_value=[node]), mock.patch.object(fast_ui, "tap_point"), \
            mock.patch.object(fast_ui, "wait_settled", return_value=True) as settled:
        result = fast_ui.execute_action({"type": "tap_label", "label": "Go", "settle": True}, "SIM", Path("/tmp"), 1, [])
    settled.assert_called_once()
    self.assertEqual(result, {"settled": True})
```

- [ ] **Step 2: Chạy để thấy fail** — Expected: 3 FAIL/ERROR.
- [ ] **Step 3: Viết `tree_signature`, `wait_settled`, đọc `settle` trong `execute_action`, thêm tham số `defaults`.**
- [ ] **Step 4: Chạy toàn bộ test** — Expected OK.
- [ ] **Step 5: Commit** `git commit -am "engine: opt-in settle after gestures"`

---

### Task 7 (A7): Action `type_text`, `launch`, `terminate`, `open_url`

**Files:**
- Modify: `scripts/fast_ui.py` (`execute_action`, `main`)
- Test: `scripts/test_fast_ui.py` (class `ActionTests`)

**Interfaces:**
- `execute_action(action, udid, artifacts, index, optional_prompt_labels, defaults: dict = {}, bundle_id: str = "")` (hai tham số mới có mặc định; `main` truyền `bundle_id`).
- `type_text`: `axe(udid, "type", required(action, "text"))`, rồi `invalidate_hierarchy`.
- `launch`: `command(["xcrun", "simctl", "launch", udid, action.get("app", bundle_id), *launch_arguments])`; `terminate`: `["xcrun", "simctl", "terminate", udid, app]` với `check=False`; `open_url`: `["xcrun", "simctl", "openurl", udid, required(action, "url")]`. Cả ba `invalidate_hierarchy`.
- Thiếu `app` và `bundle_id` rỗng → `FastUIError("action N: launch needs 'app'")`.

- [ ] **Step 1: Viết test fail**

```python
def test_simulator_lifecycle_actions_call_simctl_and_axe(self) -> None:
    with mock.patch.object(fast_ui, "command") as cmd, mock.patch.object(fast_ui, "axe") as axe:
        fast_ui.execute_action({"type": "type_text", "text": "hello"}, "SIM", Path("/tmp"), 1, [], {}, "com.x")
        fast_ui.execute_action({"type": "launch", "launch_arguments": ["-flag"]}, "SIM", Path("/tmp"), 2, [], {}, "com.x")
        fast_ui.execute_action({"type": "terminate", "app": "com.apple.Preferences"}, "SIM", Path("/tmp"), 3, [], {}, "com.x")
        fast_ui.execute_action({"type": "open_url", "url": "myapp://home"}, "SIM", Path("/tmp"), 4, [], {}, "com.x")
    axe.assert_called_once_with("SIM", "type", "hello")
    self.assertEqual(cmd.call_args_list[0].args[0], ["xcrun", "simctl", "launch", "SIM", "com.x", "-flag"])
    self.assertEqual(cmd.call_args_list[1].args[0], ["xcrun", "simctl", "terminate", "SIM", "com.apple.Preferences"])
    self.assertEqual(cmd.call_args_list[2].args[0], ["xcrun", "simctl", "openurl", "SIM", "myapp://home"])
    with self.assertRaisesRegex(fast_ui.FastUIError, "needs 'app'"):
        fast_ui.execute_action({"type": "launch"}, "SIM", Path("/tmp"), 5, [], {}, "")
```

- [ ] **Step 2: Chạy để thấy fail** — Expected: `unsupported action type 'type_text'`.
- [ ] **Step 3: Thêm bốn nhánh, hai tham số, truyền `bundle_id` từ `main`.**
- [ ] **Step 4: Chạy toàn bộ test** — Expected OK.
- [ ] **Step 5: Commit** `git commit -am "engine: type_text, launch, terminate, open_url on simulator"`

---

### Task 8 (A8): Chế độ app có sẵn (`app.prebuilt`)

**Files:**
- Modify: `scripts/fast_ui.py:598-606` (`prepare_app`), `main` (fresh_install)
- Test: `scripts/test_fast_ui.py` (class `LifecycleTests`)

**Interfaces:**
- `prepare_app(app, base, udid, reuse_app) -> tuple[Path | None, bool]`: khi `app.get("prebuilt")` là True → `ensure_booted(udid)`; nếu có `app_path` thì `verify_app` và trả `(path, False)`, nếu không trả `(None, False)`. Không đọc `derived_data`, không build.
- `main`: với `prebuilt`, mặc định `setup.fresh_install` là `False`; nếu `fresh_install` True mà `app_path` là None → `FastUIError("prebuilt app without app_path cannot be fresh-installed")`. `--build-only` với `prebuilt` in `READY task=... build=skip` và thoát 0.

- [ ] **Step 1: Viết test fail**

```python
def test_prebuilt_app_skips_build_and_derived_data(self) -> None:
    with mock.patch.object(fast_ui, "ensure_booted"), mock.patch.object(fast_ui, "build_if_needed") as build:
        app_path, built = fast_ui.prepare_app({"bundle_id": "com.apple.Preferences", "prebuilt": True}, Path("/tmp"), "SIM", False)
    build.assert_not_called()
    self.assertIsNone(app_path)
    self.assertFalse(built)
```

- [ ] **Step 2: Chạy để thấy fail** — Expected: `missing 'app_path' in app`.
- [ ] **Step 3: Sửa `prepare_app` và `main`.**
- [ ] **Step 4: Chạy toàn bộ test** — Expected OK.
- [ ] **Step 5: Chạy thật một lần** (simulator rảnh, ví dụ iPhone 17e):

Flow tạm `{"version":1,"name":"settings-smoke","app":{"bundle_id":"com.apple.Preferences","prebuilt":true,"simulator":"<UDID>","project_root":"/tmp"},"actions":[{"type":"launch"},{"type":"wait","label":"General","timeout":15},{"type":"dump","name":"settings"}]}`
Run: `fastSimulatorTest /tmp/settings-smoke.json`
Expected: dòng `PASS task=settings-smoke ... labels=[...]` và `settings-ui.json` có khoá `id` ở ít nhất một node.

- [ ] **Step 6: Commit** `git commit -am "engine: prebuilt app mode (system apps, installed builds)"`

---

### Task 9 (A9): Pillow lười

**Files:**
- Modify: `scripts/fast_ui.py:24` (import), `:692-709` (`motion_ratio`)
- Test: `scripts/test_fast_ui.py`

- [ ] **Step 1: Viết test fail**

```python
def test_engine_imports_without_pillow(self) -> None:
    import importlib, subprocess
    code = "import sys; sys.modules['PIL'] = None; import fast_ui; print('ok')"
    out = subprocess.run([sys.executable, "-c", code], cwd=str(Path(fast_ui.__file__).parent), capture_output=True, text=True)
    self.assertEqual(out.stdout.strip(), "ok")
```

- [ ] **Step 2: Chạy để thấy fail** — Expected: stdout rỗng (ImportError).
- [ ] **Step 3: Chuyển `from PIL import Image, ImageChops` vào trong `motion_ratio`; nếu ImportError → `FastUIError("motion needs Pillow: python3 -m pip install --user pillow")`.**
- [ ] **Step 4: Chạy toàn bộ test** — Expected OK.
- [ ] **Step 5: Commit** `git commit -am "engine: import Pillow only for motion"`

---

## Phase B — iPhone thật

### Task 10 (B1): `--device` khớp một phần tên

**Files:**
- Modify: `scripts/fast_device.py:70-81` (`resolve_device`)
- Test: `scripts/test_fast_ui.py` (class `DeviceLauncherTests`)

**Interfaces:**
- `resolve_device(requested)`: khớp chính xác `udid`/`name` trước; nếu không, lọc `requested.lower() in name.lower()`; đúng một → trả; nhiều → `FastDeviceError("device 'X' matches N iPhones: [...]; pass the full name or UDID")`; không có → lỗi hiện tại.

- [ ] **Step 1: Viết test fail**

```python
def test_resolve_device_matches_partial_name_only_when_unique(self) -> None:
    import fast_device
    devices = [{"udid": "A", "name": "iPhone - Blue - 27", "os": "27.0", "connected": True},
               {"udid": "B", "name": "iPhone 16 - 26.2", "os": "26.2", "connected": True},
               {"udid": "C", "name": "iPhone 16 blue 18.6.2", "os": "18.6", "connected": False}]
    with mock.patch.object(fast_device, "physical_devices", return_value=devices):
        self.assertEqual(fast_device.resolve_device("blue - 27")["udid"], "A")
        with self.assertRaisesRegex(fast_device.FastDeviceError, "matches 2 iPhones"):
            fast_device.resolve_device("iPhone 16")
```

- [ ] **Step 2: Chạy để thấy fail**; **Step 3: Sửa `resolve_device`**; **Step 4: Chạy toàn bộ test** — OK.
- [ ] **Step 5: Commit** `git commit -am "device: partial, case-insensitive device names"`

---

### Task 11 (B2): Runner đọc `identifier`/`value`, selector `id`/`value`, dump có id

**Files:**
- Modify: `device-runner/UITests/FlowRunner.swift:11-17` (`Node`), `:329-341` (`snapshotNodes`), `:371-386` (`matches`), `:192-204` (`tap_label`), `:436-454` (`visibleNodes`)

**Interfaces:**
- `Node` thêm `let identifier: String` và `let value: String` (từ `element.identifier`, `element.value as? String ?? ""`).
- `matches` thêm: `selector["id"] as? String` so với `node.identifier`; `selector["value"] as? String` so với `node.value`.
- `tap_label` lấy selector từ action theo cùng danh sách khoá như Python (`label`, `label_contains`, `id`, `value`, `element_type`, `frame`), mặc định `element_type = "Button"`, và áp dụng fallback như Task 4 (A4) (duy nhất một node cùng label khi không ghi `element_type`).
- `visibleNodes` thêm `"id"` và `"value"` khi không rỗng.

- [ ] **Step 1: Sửa Swift như trên.**
- [ ] **Step 2: Build lại runner và chạy smoke trên Settings** (iPhone đang cắm, đã mở khoá, không có runner khác: `fastDeviceTest status --device <tên>` in `IDLE`):

Run:
```bash
fastDeviceTest serve --device "<tên iPhone>" --rebuild-runner
fastDeviceTest do '[{"type":"launch"},{"type":"wait","label":"General"},{"type":"dump","name":"settings"}]' --app com.apple.Preferences --device "<tên iPhone>" --out /tmp/fd
fastDeviceTest stop --device "<tên iPhone>"
```
Expected: `PASS actions=3 ... ui=file:///tmp/fd/settings-ui.json`; file có node với khoá `"id"`.

- [ ] **Step 3: Commit** `git commit -am "runner: id/value selectors, tap_label fallback, ids in dumps"`

---

### Task 12 (B3): Tắt wait-for-idle theo flow

**Files:**
- Create: `device-runner/UITests/Quiescence.swift`
- Modify: `device-runner/UITests/FlowRunner.swift:116-125` (`runFlow`), `:66-96` (`handle`)
- Modify: `scripts/fast_device.py:291-303` (`prepare_flow`)

**Interfaces:**
- `enum Quiescence { static func disable() -> Bool; static func restore() }`: tìm `XCUIApplicationProcess` qua `NSClassFromString`, tìm `waitForQuiescenceIncludingAnimationsIdle:` rồi `waitForQuiescenceIncludingAnimationsIdle:isPreEvent:`; thay IMP bằng block trả về ngay (`imp_implementationWithBlock`), giữ IMP gốc để `restore`. Không tìm thấy → trả `false`, không crash.
- `runFlow`: nếu `setup["wait_for_idle"] as? Bool == false` → `Quiescence.disable()` trước khi launch, `defer { Quiescence.restore() }`; ghi `"wait_for_idle": false` vào report.
- Request `op: "actions"`/`"action"` nhận khoá tuỳ chọn `"wait_for_idle": false` ở cấp request; `fast_device.py` `do` truyền `--no-idle-wait` thành khoá đó.
- `prepare_flow` giữ nguyên `setup.wait_for_idle` (đã spread), không cần đổi; thêm test Python xác nhận khoá đi qua.

- [ ] **Step 1: Test Python**

```python
def test_prepare_flow_keeps_wait_for_idle(self) -> None:
    import fast_device
    prepared = fast_device.prepare_flow({"version": 1, "setup": {"wait_for_idle": False, "preferences": {"a": True}}})
    self.assertFalse(prepared["setup"]["wait_for_idle"])
```

- [ ] **Step 2: Viết Swift, rebuild runner, đo trên app A** (app có dashboard animation, đã cài):

Run hai lần cùng batch 4 tap `{"type":"tap_label","label":"<nút có thật>"}` qua `fastDeviceTest do '[...]'`, lần hai thêm `--no-idle-wait`; đọc log `~/Library/Caches/fast-device-test/server-<udid>.log`.
Expected: khoảng cách `Tap` → request kế từ ~2.8 s xuống < 1.0 s; cả hai lần PASS.

- [ ] **Step 3: Chạy toàn bộ test Python** — OK. **Step 4: Commit** `git commit -am "runner: optional wait_for_idle=false via quiescence swizzle"`

---

## Phase C — Review

### Task 13 (C1): Biên dịch helper Swift một lần

**Files:**
- Modify: `scripts/fast_ui_review.py:150-166` (`extract`, `durations`), `:330-335` (`main`)
- Test: `scripts/test_fast_ui_review.py`

**Interfaces:**
- `helper_command(source: str, cache_dir: Path) -> list[str]`: `digest = sha1(source)[:12]`; binary `cache_dir / f"frames-{digest}"`; nếu chưa có thì ghi `frames-{digest}.swift` và chạy `swiftc -O <swift> -o <binary>`; thành công → `[str(binary)]`; thất bại → `["swift", str(swift_file)]`.
- `cache_dir` mặc định `Path.home() / "Library/Caches/fast-ios-device-test"`; `extract`/`durations` nhận `helper: list[str]` thay cho `Path`.

- [ ] **Step 1: Viết test fail**

```python
def test_helper_is_compiled_once_and_reused(self) -> None:
    with tempfile.TemporaryDirectory() as raw, mock.patch.object(review.subprocess, "run") as run:
        run.return_value.returncode = 0
        cache = Path(raw)
        first = review.helper_command("print(1)", cache)
        Path(first[0]).write_text("")  # giả lập swiftc đã tạo binary
        second = review.helper_command("print(1)", cache)
    self.assertEqual(first, second)
    self.assertEqual(run.call_count, 1)
    self.assertEqual(run.call_args.args[0][0], "swiftc")
```

- [ ] **Step 2: Chạy để thấy fail** — `python3 -m unittest test_fast_ui_review -v`, Expected: AttributeError.
- [ ] **Step 3: Viết `helper_command`, đổi chữ ký `extract`/`durations`, sửa `main`.**
- [ ] **Step 4: Chạy toàn bộ test** — OK. Chạy thật `fastUIReview --root <root có session cũ> --session <name>` hai lần: lần hai nhanh hơn lần đầu ≥ 3 s.
- [ ] **Step 5: Commit** `git commit -am "review: compile the AVFoundation helper once"`

---

## Phase D — Tài liệu, installer, đóng gói

### Task 14 (D1): Tài liệu skill

**Files:**
- Modify: `skills/fast-ios-device-test/SKILL.md`, `skills/fast-ios-device-test/references/usage.md`, `references/device.md`, `commands/fastSimulatorTest.md`, `commands/fastDeviceTest.md`

**Nội dung phải có:**
- SKILL.md thêm mục "Chọn tool" đúng ba dòng: chưa biết màn hình, cần pinch/drag/xoay/log → subagent Xcode MCP (skill `device-interaction`), trên simulator khác; cần chứng minh, lặp lại, matrix, video → tool này; hai bên không dùng chung simulator.
- Selector mới `id`, `value`; action mới `type_text`, `launch`, `terminate`, `open_url`; khoá `settle`, `app.prebuilt`, `setup.wait_for_idle`; ý nghĩa `fallback_type` trong kết quả và dòng gợi ý trong FAIL.
- Quy tắc timeout, post_delay, hai lần rerun chỉ còn trong SKILL.md; `commands/*.md` chỉ giữ `$ARGUMENTS`, lệnh engine và "đọc SKILL.md". Bảng action chi tiết chỉ trong usage.md.
- Mục tiêu: SKILL.md ≤ 1000 từ, mỗi command ≤ 120 từ.

- [ ] **Step 1: Baseline** — trước khi sửa, dispatch một subagent `sonnet` với prompt: "Dùng skill fast-ios-device-test, viết flow kiểm tra màn Settings › General trên simulator <UDID> bằng app có sẵn com.apple.Preferences và chạy nó." Ghi lại: nó có dùng `app.prebuilt` không, có `dump` trước khi đoán label không, có vượt timeout 8 s không.
- [ ] **Step 2: Sửa tài liệu theo nội dung trên**; kiểm `wc -w`.
- [ ] **Step 3: Chạy lại cùng prompt với subagent mới**; Expected: dùng `prebuilt`, timeout trong giới hạn, trả một dòng PASS.
- [ ] **Step 4: Commit** `git commit -am "docs: tool selection rule, new selectors and actions, dedupe commands"`

---

### Task 15 (D2): Installer tự chứa

**Files:**
- Create: `vendor/AXe-macOS-v1.8.0-universal.tar.gz` (tải từ GitHub release, 8.4 MB), `vendor/AXe-LICENSE`
- Create: `device-runner/FastDeviceRunner.xcodeproj` (sinh bằng `xcodegen generate` trong `device-runner/`)
- Modify: `install.sh`, `scripts/fast_device.py:202-233` (`build_runner`), `README.md`, `GUIDE.md`

**Interfaces:**
- `install.sh`: nếu thiếu `axe` hoặc Xcode ≥ 27 mà `axe --version` < 1.8.0 → giải nén `vendor/AXe-*.tar.gz` vào `~/.local/share/axe` và ghi launcher `~/.local/bin/axe` (`exec "$HOME/.local/share/axe/axe" "$@"`); chỉ gọi Homebrew khi không có tarball. Bỏ cài `xcodegen`. Pillow: cài nếu được, thất bại chỉ cảnh báo.
- `install.sh --check`: in `xcode=`, `axe=`, `python=`, `pillow=yes|no`, `xcodegen=yes|no (optional)`, `profiles=<số development profile hợp lệ>`, kết thúc `CHECK OK` hoặc liệt kê thứ thiếu; không ghi gì.
- `build_runner`: nếu `RUNNER_SOURCE / "FastDeviceRunner.xcodeproj"` tồn tại thì copy nó và bỏ qua `xcodegen`; `runner_fingerprint` thêm cả `.pbxproj`.
- README/GUIDE: mục "Máy mới" ba bước; mục "Xcode MCP" một lệnh `claude mcp add xcode -- xcrun mcpbridge`.

- [ ] **Step 1: Tải tarball và sinh xcodeproj**

Run:
```bash
cd ~/Resources/Tool/fast-ios-device-test && mkdir -p vendor && gh release download v1.8.0 --repo cameroncooke/AXe --pattern 'AXe-macOS-v1.8.0-universal.tar.gz' --dir vendor
curl -sL https://raw.githubusercontent.com/cameroncooke/AXe/main/LICENSE -o vendor/AXe-LICENSE
cd device-runner && xcodegen generate --quiet && ls FastDeviceRunner.xcodeproj
```

- [ ] **Step 2: Test Python cho `build_runner`**

```python
def test_build_runner_uses_committed_xcodeproj_without_xcodegen(self) -> None:
    import fast_device
    with tempfile.TemporaryDirectory() as raw, mock.patch.object(fast_device, "RUNNER_SOURCE", Path(raw) / "src"), \
            mock.patch.object(fast_device, "CACHE_ROOT", Path(raw) / "cache"), \
            mock.patch.object(fast_device.shutil, "which", return_value=None), \
            mock.patch.object(fast_device, "run") as run, mock.patch.object(fast_device, "sign_runner"):
        (Path(raw) / "src" / "UITests").mkdir(parents=True)
        (Path(raw) / "src" / "project.yml").write_text("name: x\n")
        (Path(raw) / "src" / "FastDeviceRunner.xcodeproj").mkdir()
        run.return_value.returncode = 0
        products = Path(raw) / "cache"
        with self.assertRaises(StopIteration):  # không có .xctestrun giả, nhưng đã qua bước xcodegen
            fast_device.build_runner("/Applications/Xcode.app/Contents/Developer", {"uuid": "u"}, False)
    self.assertNotIn("xcodegen", [call.args[0][0] for call in run.call_args_list])
```

- [ ] **Step 3: Sửa `install.sh`, `build_runner`, README, GUIDE.**
- [ ] **Step 4: Cài thử vào thư mục tạm**

Run:
```bash
S=$(mktemp -d) && env FAST_IOS_INSTALL_DIR="$S/share" CLAUDE_SKILLS_DIR="$S/skills" CLAUDE_COMMANDS_DIR="$S/commands" FAST_IOS_BIN_DIR="$S/bin" bash install.sh && bash install.sh --check
```
Expected: `engine self-test: OK`, `CHECK OK`, thời gian < 10 s.

- [ ] **Step 5: Commit** `git commit -am "install: bundled AXe, committed xcodeproj, --check"`

---

### Task 16 (D3): Phiên bản 1.2.0 và gói chia sẻ

**Files:**
- Modify: `.claude-plugin/plugin.json` (`"version": "1.2.0"`), `.claude-plugin/marketplace.json`, `README.md` (changelog 1.2.0)
- Create: `make-zip.sh`

**Interfaces:**
- `make-zip.sh`: `zip -r fast-ios-device-test-<version>.zip fast-ios-device-test -x '*.DS_Store' -x '*__pycache__*' -x '*/.git/*' -x '*/build/*'` từ thư mục cha; in đường dẫn và kích thước.

- [ ] **Step 1: Sửa version và changelog** (8 dòng: FAIL có type và gợi ý, dump gọn, `id`/`value`, cache, `settle`, action mới, `prebuilt`, `wait_for_idle`, review nhanh, installer tự chứa).
- [ ] **Step 2: Chạy toàn bộ test lần cuối** — `cd scripts && python3 -m unittest test_fast_ui test_fast_ui_review`, Expected OK.
- [ ] **Step 3: Tạo zip**

Run: `bash make-zip.sh`
Expected: `~/Resources/Tool/fast-ios-device-test-1.2.0.zip`, khoảng 8.6 MB.

- [ ] **Step 4: Commit và tag** `git commit -am "release 1.2.0" && git tag v1.2.0`
- [ ] **Step 5: Cập nhật memory** `~/.claude/projects/-Users-sonmacmini/memory/ios-test-tooling-setup.md`: bản 1.2.0, có git và zip backup.

---

## Thứ tự và điểm dừng

A1 → A2 → A3 → A4 → A5 → A6 → A7 → A8 → A9 (mỗi task một commit, dừng được sau bất kỳ task nào, tool vẫn chạy). B1 → B2 → B3 cần iPhone cắm và mở khoá. C1 độc lập. D1 sau A và B để tài liệu khớp mã. D2 → D3 cuối cùng.
