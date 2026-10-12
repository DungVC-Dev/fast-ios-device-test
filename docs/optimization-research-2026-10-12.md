# fast-ios-device-test — nghiên cứu tối ưu (2026-10-12)

Trạng thái: nghiên cứu, chưa sửa gì trong tool. Bản cài đang dùng là 1.1.0 có vá Xcode 27,
live tại `~/Resources/Tool/fast-ios-device-test` (symlink vào `~/.claude/skills`,
`~/.claude/commands`, `~/.local/bin`). 53 unit test pass
(`cd scripts && python3 -m unittest test_fast_ui test_fast_ui_review`).
Chưa có bản zip backup của bản đã vá: tạo backup trước khi sửa engine.

## 1. Phương pháp

"app A" trong tài liệu này là một app thật của công ty (dashboard có animation); tên app, tên thiết bị và bundle id đã được bỏ khỏi tài liệu vì không cần cho tool.

- Đọc toàn bộ mã: `scripts/fast_ui.py` (engine simulator), `scripts/fast_device.py` +
  `device-runner/UITests/FlowRunner.swift` (iPhone thật), `fast_ui_review.py`,
  `fast_ui_report.py`, SKILL.md, references, commands, install.sh.
- Đào transcript 63 session đã dùng tool (`~/.claude/projects/*/*.jsonl`).
- Đọc log runner iPhone (`~/Library/Caches/fast-device-test/server-*.log`) và metrics.json
  của các lần chạy cũ trong `<project>/build/fast-ui`.
- Boot tạm simulator iPhone 17 (98018DC4) để đo từng lệnh nền, tắt sau khi đo.
- Môi trường: Xcode 27.0 (27A266a), macOS 27.0.1, AXe 1.8.0, `python3` = Xcode 3.9.6, Pillow 11.3.

## 2. Số liệu đo được

| Chỉ số | Giá trị |
|---|---|
| Lỗi FAIL phổ biến nhất trong transcript | "timed out waiting for UI selector": ~20/22 lần FAIL |
| Lần gọi trong transcript | fastSimulatorTest 956, fastDeviceTest 834 (`do` 247, `stop` 197, `serve` 50), fastUIReview 550, fastUIReport 95 |
| `axe describe-ui` (home screen / Settings) | 0.9–2.7 s mỗi lần, JSON 300–380 KB, ~250 node thật |
| `axe tap -x -y` trần | 1.0 s (khởi tạo session) + post-delay; 0.4 s settle dưới Device Hub bắt buộc |
| `axe tap --label X --wait-timeout 8` | FAIL rc=1 sau 12 s dù nút đang hiện → không dùng được |
| `xcrun simctl io screenshot` | 0.5–0.7 s |
| `simctl ui appearance`, `defaults write` | 0.2–0.35 s mỗi lệnh |
| Một action trên simulator | ≈ 2–2.5 s (describe-ui + tap) |
| Một flow simulator đã cache app (transcript) | 6–12 s; fresh_install 1.6–2 s, launch ~1 s |
| Build lần đầu (app A) | prepare 54 s, fresh_install 9 s |
| iPhone thật: XCUITest "wait for idle" sau mỗi tap (app A) | 2.4–2.6 s, 12/14 mẫu |
| iPhone thật: snapshot hierarchy | ~0.4–0.7 s, 2 lần mỗi `do` |
| `fastDeviceTest status` (overhead Python + devicectl + ping) | 0.2–0.6 s |
| `failure-ui.json` của 1 lần FAIL | 11 MB cho 590 node |
| `swift frames.swift` trong fastUIReview | 4.1 s lần đầu, 0.3 s sau; `swiftc` 1 s rồi 0.03 s/lần |
| Tài liệu agent nạp mỗi lần gọi | SKILL.md ≈ 1.9k token, usage.md ≈ 2.7k, command ≈ 0.3–0.45k |

Ví dụ thực tế (app A, 2026-10-05, task `slot-menu-trash@dark`): 3 lần FAIL liên tiếp,
mỗi lần 20 s timeout ở selector sai. Hierarchy lúc đó: 81 StaticText, 87 Image, 38 Button;
`tap_label` chỉ khớp Button và dòng FAIL không in type.

## 3. Vấn đề tìm thấy trong mã

1. `tap_label` mặc định chỉ khớp `element_type: Button`; dòng FAIL liệt kê label không kèm
   type; không gợi ý label gần giống. Đây là nguồn rerun lớn nhất.
2. `flatten()` trong fast_ui.py duyệt mọi dict con, nên dict `frame` cũng thành "node"
   (sample node chỉ có x, y, width, height). `dump` và `failure-ui.json` ghi node còn nguyên
   `children` lồng nhau → kích thước tăng theo độ sâu cây (11 MB).
3. Engine bỏ qua `AXUniqueId` (accessibilityIdentifier) và `AXValue`; FlowRunner.swift cũng
   không đọc `identifier`/`value` của XCUIElementSnapshot. Không có selector `id`, `value`.
4. `tap_label` (cả hai engine) không nhận `label_contains`; simulator cũng không nhận `frame`.
5. Engine simulator thiếu `type_text`, `launch`, `terminate`, `open_url`; luôn đòi
   `project`, `derived_data`, `app_path` nên không test được Settings hay app đã cài sẵn.
6. `step_labels` khi `--record` gọi thêm một `describe-ui` mỗi bước (~1 s/bước).
7. fastUIReview chạy `swift` interpreter mỗi video thay vì biên dịch helper một lần.
8. Quy tắc timeout / post_delay / hai lần rerun lặp ở `commands/*.md` và SKILL.md.
9. `resolve_device` chỉ khớp tên chính xác; "Blue" không khớp "iPhone - Blue - 27".
10. Memory cũ ghi có `fast-ios-device-test-1.1.0.zip`: sai, file không tồn tại.

## 4. Đề xuất theo ưu tiên

| # | Việc | Lợi ích | Phạm vi |
|---|---|---|---|
| 1 | FAIL in `label (Type)`, gợi ý label gần giống (difflib), `tap_label` fallback sang node duy nhất cùng label khi không có Button | Giảm rerun 20 s mỗi lần, chính xác hơn | fast_ui.py, FlowRunner.swift |
| 2 | Dump gọn: chỉ label, type, id, value, frame; lọc dict frame khỏi `flatten` | 11 MB → vài chục KB; tránh cháy context | fast_ui.py |
| 3 | Selector `id`, `value` ở cả hai engine | Ổn định hơn label; kiểm được trạng thái switch, text field | cả hai engine |
| 4 | Cache hierarchy TTL ~300 ms sau `wait`; bỏ describe-ui thừa trong `step_labels` | ~1 s mỗi cặp wait→tap | fast_ui.py |
| 5 | Tuỳ chọn tắt wait-for-idle trong runner iPhone (swizzle `-[XCUIApplicationProcess waitForQuiescenceIncludingAnimationsIdle:]` như WebDriverAgent; API private) | ~2.4 s mỗi tap trên màn có animation | FlowRunner.swift, cần `--rebuild-runner` |
| 6 | Simulator: `type_text`, `launch`, `terminate`, `open_url`; chế độ app có sẵn (không cần project) | Đa dụng: Settings, deep link, app đã cài | fast_ui.py |
| 7 | fastUIReview: `swiftc` helper một lần vào cache | 4 s → 1 s lần đầu, 0.3 → 0.03 s mỗi video | fast_ui_review.py |
| 8 | Gộp quy tắc trùng; bảng tham chiếu sang usage.md; engine tự tìm `app_path` trong derived_data | Bớt 1.5–2k token mỗi lần gọi, bớt lỗi boilerplate | docs, fast_ui.py |
| 9 | `--device` khớp một phần tên, không phân biệt hoa thường | Tiện | fast_device.py |

Thứ tự làm: 1, 2, 3 (Python có test, rủi ro thấp) → 4, 6, 7 → 5 (Swift, private API) → 8, 9.

## 5. Đã thử và không nên làm

- `axe tap --label --wait-timeout`: không tìm được nút đang hiện (rc=1 sau 12 s). Giữ thiết
  kế describe-ui rồi tap theo frame.
- `axe batch`: không chèn được `wait`/assert giữa các bước.
- AXe mới hơn 1.8.0: chưa có (GitHub releases 2026-10-12), chưa có fix tap rơi dưới Device Hub.
- Giảm sleep 0.12 s trong vòng poll: vô nghĩa vì mỗi poll đã mất ~1 s ở AXe.

---

# Phần 2 — Khảo sát bên ngoài và Xcode MCP chính chủ

## 7. Xcode 27 MCP (`xcrun mcpbridge`) — đo trực tiếp trên máy này

Bộ tool `DeviceInteraction*` của Apple: `StartSession` (không workspace, chỉ app đã cài) /
`StartWorkspaceSession` (gắn project, cho phép `InstallAndRun` build + cài + chạy) →
`Synthesize` (một lệnh tương tác, trả về screenshot + thumbnail + hierarchy + log) →
`EndSession`. Lệnh: `t x y [dur]`, `d x y`, `t x1 y1 f x2 y2 dur` (swipe), `drag`, `mt [...]`
(multi-touch, pinch), `b h/p/u/d` (nút cứng), `sender keyboard kbd <text>` (Unicode escape),
`w dur`, `orientation ...`. Skill chính chủ `device-interaction` (1.9k từ, export bằng
`xcrun agent skills export`) bắt buộc tương tác qua **subagent**, luôn tap theo `hitPoint`
trong hierarchy, capture trước và sau mỗi bước, retry một lần rồi báo lỗi.

Đo trên simulator iPhone 17 (iOS 27.0), session không workspace:

| Bước | Thời gian | Ghi chú |
|---|---|---|
| Capture đầu (hierarchy + screenshot) | 2.1–2.3 s | hierarchy 14 KB text, 187 dòng ≈ 2k token |
| Capture khi session đã ấm | 0.9–1.0 s | hierarchy 4 KB (Reminders) |
| Tap + capture sau tap | 3.1 s | mở app Reminders |
| Nút Home + capture | 6.2 s | chờ animation |

Hierarchy là text thụt dòng kiểu XCUITest: `Icon, {{x, y}, {w, h}}, identifier: 'Watch',
label: 'Watch', hitPoint: {154.7, 133.3}`, gọn hơn nhiều so với JSON 380 KB của AXe.

Giới hạn thấy được:

- Không có `wait` theo selector: muốn chờ một label xuất hiện, agent phải tự lặp capture,
  mỗi vòng là một tool call (~1 s) cộng đọc file hierarchy (~1–2k token). Tool của mình
  poll trong Python và trả về một dòng PASS/FAIL cho cả flow.
- Không tap theo label/id, chỉ theo toạ độ `hitPoint`; không fresh install, không seed
  UserDefaults, không appearance/content-size, không quay video, không matrix, không report.
- Session không workspace trên máy này chỉ liệt kê simulator iOS 27.0; không chọn được
  iPhone thật (các iPhone đang cắm chạy iOS 26.x). Muốn chạy máy thật phải dùng
  `StartWorkspaceSession` trên project (chưa thử).
- Cần Xcode/mcpbridge; Apple ghi rõ session "expensive", phải đóng sớm.

Điểm Xcode MCP hơn tool mình: pinch/drag/multi-touch, nút cứng, xoay máy, gõ Unicode,
đọc console log app (`GetConsoleOutput`), build + cài qua Xcode không cần cấu hình gì,
hierarchy có sẵn `identifier` và `hitPoint`.

**Kết luận:** Xcode MCP là công cụ *khám phá* cho agent ("mở thử, bấm thử, xem gì đang
hiện"); tool mình là *runner kiểm chứng lặp lại* (flow JSON, assert, matrix, video, báo cáo).
Không thay thế nhau, nên dùng kết hợp: khám phá bằng Xcode MCP khi chưa biết màn hình hoặc
cần gesture phức tạp, rồi chốt thành flow chạy bằng `fastSimulatorTest`/`fastDeviceTest`.

## 8. MobileBuildMCP 2.7 (tên cũ XcodeBuildMCP, getsentry)

Dưới nền vẫn là `axe describe-ui`, nên không nhanh hơn engine mình ở từng poll. Thiết kế
đáng mượn (đọc từ `src/mcp/tools/ui-automation/shared/*`):

- **Post-action settled snapshot**: sau mỗi action, poll `describe-ui` mỗi 100 ms cho tới
  khi hai snapshot liên tiếp có cùng "signature" phần tử trong ≥100 ms (timeout 2.5 s), thay
  cho `post_delay` cố định.
- `wait_for_ui` với predicate `exists | gone | enabled | focused | textContains | settled`;
  selector `elementRef | identifier | label | role | value`.
- Semantic tap ưu tiên `--id` > `--label` > `--value` kèm `--element-type`, fallback toạ độ
  khi AXe báo "multiple/no accessibility element matched". Với SwiftUI `Switch` dùng
  `touch --down --up` thay vì `tap` (tap thường không đổi được toggle trên iOS 26+).
- Element ref có hạn dùng; cảnh báo "snapshot stale" khi tái dùng ref cũ.
- 2.7.0: chạy được với Device Hub trên Xcode 27; không ghi fix nào cho tap rơi. Rủi ro mới:
  AXe issue #74, tap không tới màn trong của iPhone Duo (gập) trên Xcode 27.1.

## 9. Maestro

Flow YAML, auto-wait, "embraces instability", có MCP server trong CLI. README chính thức
vẫn ghi **chưa hỗ trợ iPhone thật**; đường vòng là maestro-runner/DeviceLab (cộng đồng) hoặc
device farm (TestingBot, BrowserStack). Tool mình đã có máy thật với runner ~5 s, nên không
đáng chuyển. Ý tưởng mượn: `runFlow` sub-flow + biến môi trường (ví dụ "qua paywall" thành
sub-flow dùng chung), `repeat`, tag để chọn bộ smoke, `extendedWaitUntil`.

## 10. WebDriverAgent: cách tắt wait-for-idle (đã xác minh mã nguồn)

`XCUIApplicationProcess+FBQuiescence.m` swizzle `waitForQuiescenceIncludingAnimationsIdle:`
(hoặc `...:isPreEvent:` trên Xcode mới hơn, chọn theo `respondsToSelector` lúc chạy, không
kiểm tra version Xcode). Bản thay thế bỏ qua hàm gốc khi `fb_shouldWaitForQuiescence == NO`
hoặc `waitForIdleTimeout ≈ 0`; nếu không thì gọi hàm gốc trong một timeout giới hạn.
Áp dụng cho `FlowRunner.swift`: swizzle qua ObjC runtime, bật bằng `setup.wait_for_idle:
false` hoặc giới hạn `wait_for_idle_timeout` (mặc định ví dụ 1 s thay vì vô hạn); nếu không
tìm thấy selector thì im lặng bỏ qua. Lợi đo được: ~2.4 s mỗi tap trên app A.

## 11. Bảng so sánh

| Tiêu chí | fast-ios-device-test | Xcode 27 MCP | MobileBuildMCP | Maestro |
|---|---|---|---|---|
| Mỗi bước simulator | ~2–2.5 s | ~1 s capture, ~3 s tap+capture | ~2–3 s (AXe + settle) | ~1–2 s (driver riêng) |
| Chờ selector / assert | có, trong engine | agent tự lặp | `wait_for_ui` | auto-wait |
| Token mỗi bước | 0 (một dòng/flow) | ~2k (đọc hierarchy) | ~1–2k (snapshot) | 0 (YAML) |
| Fresh install + seed UserDefaults | có | không | một phần | không |
| Dark / Dynamic Type matrix | có | không | không | không |
| Video + review + report | có | không | không | video có |
| iPhone thật | có (runner 5 s) | cần workspace session, chưa thử | không | chưa chính thức |
| Pinch / drag / nút cứng / xoay | thiếu | có | có (gesture, button) | có |
| Console log app | không | có | có | không |
| Cần Xcode mở | không | có (mcpbridge) | không | không |

## 12. Nên làm gì tiếp (bổ sung cho mục 4)

A. **Giữ engine riêng, mượn 5 ý tưởng**: (1) selector `id`, `value`, `role`; predicate
   `enabled`, `focused`, `label_contains` cho mọi action; (2) "settled" sau action thay
   `post_delay` cố định; (3) `dump` xuất text thụt dòng kèm `hitPoint` và `id` theo định dạng
   của Apple, vài KB thay vì 11 MB; (4) `touch down/up` cho Switch; (5) cache hierarchy có TTL.
B. **Quy tắc chọn tool ghi vào SKILL.md**: chưa biết màn hình, cần pinch/drag/xoay/log → subagent
   Xcode MCP (skill `device-interaction`); cần chứng minh, lặp lại, matrix, video → tool mình.
   Hai bên dùng chung một simulator là xung đột (Xcode cài đè app), nên tách simulator.
C. **Máy thật**: swizzle quiescence (mục 10); khi `no usable development profile` (đã gặp 2 lần
   trong transcript) thử `DeviceInteractionStartWorkspaceSession` của Xcode MCP làm đường dự phòng.
D. **Quy trình auto test**: boot simulator + `--build-only` ngay đầu session, song song với lúc
   viết flow (Apple cũng khuyên "start session early"); một simulator riêng cho agent; lưu flow
   tái dùng theo project (`<project>/fast-ui/flows/`, có sub-flow) để `fastUIReport` chạy bộ
   smoke trước PR; FAIL in kèm type và gợi ý để không rerun mù.
E. **Theo dõi**: AXe #74 (iPhone gập), Xcode 27.1 đổi Device Hub, private API quiescence.

## 13. Phạm vi áp dụng và cách đóng gói (đã chốt)

- **Áp dụng cho mọi dự án ngay**: engine không biết gì về dự án, mọi thứ nằm trong flow JSON
  agent viết lúc chạy. Đã kiểm tra: không dự án nào có file cấu hình riêng của tool. Ghi chú
  theo dự án trong memory (ví dụ app A cần một profile ký riêng cho runner) vẫn đúng sau khi
  tối ưu. Bộ flow smoke tái dùng theo dự án (`<project>/fast-ui/flows/`) là tuỳ chọn về sau.
- **Mọi thay đổi nằm trong `~/Resources/Tool/fast-ios-device-test`**: `~/.claude/skills`,
  `~/.claude/commands`, `~/.local/bin` chỉ là symlink. Runner iPhone trong `~/Library/Caches`
  tự build lại khi mã Swift đổi. Hai thứ bản chất nằm ngoài gói: AXe (sẽ đóng kèm tarball) và
  đăng ký Xcode MCP trên máy mới (`claude mcp add xcode -- xcrun mcpbridge`, ghi vào README).
- Quy tắc chọn tool (Xcode MCP để khám phá, tool này để kiểm chứng) viết vào SKILL.md để đi
  theo gói, không sửa CLAUDE.md toàn cục.
- Bản tối ưu là **1.2.0**; tạo zip backup bản 1.1.0 đang chạy trước khi sửa, và `git init`
  trong thư mục tool để có lịch sử (hiện chưa có git, chưa có backup).

## 14. Được gì, mất gì

| Hạng mục | Trước | Sau |
|---|---|---|
| Sai selector | FAIL chỉ in label, agent đoán mù, 3 lần × 20 s | FAIL in `label (Type)` + gợi ý gần giống; `tap_label` tự tap node duy nhất cùng label |
| File dump khi FAIL | 11 MB | vài chục KB, JSON phẳng có `center` |
| Cách chọn phần tử | label, type, frame | thêm `id`, `value`, `label_contains` ở mọi action |
| Simulator, mỗi cặp wait→tap | ~2.5 s | ~1.5 s nhờ cache hierarchy 300 ms |
| iPhone thật, màn hình có animation | +2.4 s mỗi tap | ~0 khi `wait_for_idle: false` |
| Loại test trên simulator | app phải build từ project | thêm `type_text`, `open_url`, `launch`/`terminate`, app cài sẵn |
| Token tài liệu mỗi lần gọi | ~4.6k | ~3k |
| Review video | 4 s khởi động mỗi lần | ~1 s một lần duy nhất |

Rủi ro và cách chặn:

- "settled" sau action có thể chậm hơn `post_delay` cố định trên màn hình không bao giờ đứng
  yên (GIF trên dashboard app A) → **opt-in theo action**, timeout 2.5 s, không bật mặc định.
- `tap_label` fallback ngoài Button có thể bấm nhầm → chỉ khi đúng **một** node khớp label và
  action không ghi `element_type`; ghi rõ `fallback_type` vào kết quả.
- Tắt wait-for-idle dùng API private → chỉ swizzle khi flow yêu cầu, tìm selector lúc chạy,
  không thấy thì bỏ qua im lặng; phải `--rebuild-runner`.
- Cache hierarchy → hạn dùng 300 ms, xoá sau mọi tap/swipe/launch.
- Rút gọn tài liệu → kiểm bằng cách chạy một subagent trước và sau khi sửa (writing-skills).
- Mã nhiều hơn → mỗi thay đổi engine đi kèm unit test; giữ tương thích Python 3.9 của Xcode;
  khi đồng nghiệp gửi bản mới vẫn phải port tay.

## 15. Cài đặt cho máy khác

Đo trên máy này: gói zip 130 KB; `install.sh` khi đã có axe, xcodegen, Pillow chạy 0.8 s
(copy, 8 symlink, tự chạy 53 unit test). Trên máy mới hoàn toàn, Homebrew cài AXe (8 MB) và
xcodegen mất 1–2 phút mỗi thứ, Pillow ~30 s; tổng 3–5 phút nếu Homebrew bình thường. Rủi ro
lớn nhất: macOS 27 với Command Line Tools cũ hơn 27 làm Homebrew từ chối cài (đã xảy ra ở
máy này). Lần chạy đầu mỗi dự án mới là phần chờ thật: boot simulator 20–40 s, build lần đầu
(54 s với app A), fresh install lần đầu 9 s; máy thật thêm 1–2 phút build runner và cần
development profile chứa chiếc iPhone đó (`FAST_DEVICE_PROFILE`).

Để cài dưới 1 phút: (1) đóng kèm `AXe-macOS-v1.8.0-universal.tar.gz` (8.4 MB, MIT) trong
`vendor/`, `install.sh` giải nén vào `~/.local/share/axe`; (2) commit sẵn
`device-runner/FastDeviceRunner.xcodeproj` để bỏ xcodegen; (3) import Pillow lười, flow
simulator chạy được khi chưa có Pillow; (4) `install.sh --check` in version Xcode, AXe,
Python, profile ký và thứ còn thiếu.

## 16. Kế hoạch triển khai

Kế hoạch chi tiết theo từng task, có test và lệnh kiểm tra:
[plans/2026-10-12-optimization-plan.md](plans/2026-10-12-optimization-plan.md).

---

# Phần 3 — Kết quả thực hiện (2026-10-12, bản 1.2.0)

Toàn bộ 17 task trong kế hoạch đã làm xong theo TDD, mỗi task một commit trên nhánh
`optimize-1.2.0` (git khởi tạo từ bản 1.1.0 đang cài), tag `v1.2.0`. Unit test: 53 → 77,
chạy bằng `cd scripts && python3 -m unittest test_fast_ui test_fast_ui_review`. Reviewer độc
lập (model mạnh nhất, ngữ cảnh mới) đọc toàn bộ diff: 0 Critical, 3 Important, 7 Minor; cả 3
Important và 1 Minor nâng hạng đã sửa trong một vòng, có test đỏ trước; 6 Minor còn lại ghi
trong ledger `docs/plans/2026-10-12-optimization-ledger.md` để làm ở 1.2.1.

## 18. Đã làm được gì (đo lại sau khi sửa)

| Hạng mục | Kết quả |
|---|---|
| FAIL tự giải thích | `visible labels: [Add Widget (StaticText), …]`, thêm `'X' exists as StaticText, not Button` hoặc `closest labels: […]` |
| `tap_label` fallback | tap node duy nhất cùng label khi không ghi `element_type`, trả `fallback_type`; không bao giờ tap vào Application/Window; trên iPhone gộp các container lồng cùng frame (kiểm chứng trên Settings: `fallback_type: StaticText`) |
| Dump | file FAIL thật từ 11 MB → 47 KB (295 node); dump Settings 166 node / 30 id / 26 KB |
| Selector | thêm `id`, `value`; `tap_label` nhận mọi khoá; kiểm chứng trên iPhone (tap theo `id=com.apple.settings.general`, chờ theo `value`) |
| Cache hierarchy | tái dùng cây < 300 ms ở poll đầu của tap; xoá sau mọi gesture/launch |
| `settle` | opt-in theo action hoặc `setup.settle_after_actions`, timeout 2.5 s, không bao giờ làm FAIL |
| Action mới (simulator) | `type_text`, `launch`, `terminate`, `open_url`; `app.prebuilt` chạy Settings không cần project (PASS 70 s kể cả boot, lần sau ~12 s) |
| AXe session flake | retry một lần khi "Timed out creating the simulator remote automation session" (gặp trong baseline) |
| iPhone | `wait_for_idle: false` / `do --no-idle-wait` (runner báo `wait_for_idle: false`, selector private tìm thấy trên Xcode 27.0 / iOS 26.6.1); `--device` khớp một phần tên |
| Review | helper Swift biên dịch một lần vào `~/Library/Caches/fast-ios-device-test` |
| Tài liệu | SKILL.md 1366 → 887 từ, command 316 → 158 và 231 → 135 từ; có quy tắc chọn Xcode MCP hay tool này; subagent sau khi sửa tìm thấy `prebuilt` trong SKILL.md, PASS lần đầu, 3 tool call thay vì 8 |
| Cài đặt | AXe 1.8.0 đóng kèm trong `vendor/`, `.xcodeproj` commit sẵn, Pillow tuỳ chọn, `install.sh --check`; cài thử máy sạch 0.8 s; không Homebrew, không xcodegen |
| Gói | `make-zip.sh` → `~/Resources/Tool/fast-ios-device-test-1.2.0.zip` (8.1 MB); backup bản cũ `fast-ios-device-test-1.1.0-backup.zip` |

## 19. Chưa đo được / còn để lại

- Lợi ích thời gian của `wait_for_idle: false` trên dashboard có animation không đo lại được
  trong phiên này vì app DEV cứ hiện paywall sau mỗi lần launch; bằng chứng là runner báo đã
  swizzle và flow chạy đúng ở cả hai chế độ. Số 2.4 s/tap vẫn là số đo từ log ngày 12/10 buổi sáng.
- 6 Minor của reviewer (xem ledger): docs bảo flow prebuilt bắt đầu bằng `launch` dù engine đã
  launch; `.xcodeproj` cũ build im lặng khi `project.yml` đổi; `Quiescence.disable()` cấp IMP
  mới mỗi lần; một test in ra stdout; `install.sh` không cảnh báo khi axe cũ đứng trước trên
  PATH; câu gợi ý "add element_type" khi selector đã có element_type.
- Ý tưởng ngoài kế hoạch chưa làm: `touch down/up` cho Switch, predicate `enabled`/`focused`,
  engine tự tìm `app_path`, thư viện flow theo dự án, đăng ký Xcode MCP trong `install.sh`.

## 20. Dùng và chia sẻ

- Máy này: bản live đã là 1.2.0 (symlink không đổi). Mở lại Claude Code để nạp SKILL.md mới.
- Máy khác: gửi `fast-ios-device-test-1.2.0.zip`, giải nén, chạy `install.sh`, mở lại Claude
  Code; `install.sh --check` để tự chẩn đoán. Xcode MCP (tuỳ chọn): `claude mcp add xcode -- xcrun mcpbridge`.
- Khi đồng nghiệp gửi bản mới của họ: port lên nhánh git này thay vì cài đè.

## 17. Nguồn

- AXe releases: https://github.com/cameroncooke/AXe/releases ; issue #74: https://github.com/cameroncooke/AXe/issues/74
- Xcode 27 MCP (bài hướng dẫn): https://crunchybagel.com/enabling-the-xcode-27-mcp-server-in-claude-code/ ;
  https://vincenzopascarella.medium.com/using-xcode-mcp-ai-powered-ios-development-3eb091698864 ;
  https://wendyliga.com/blog/how-to-use-xcode-27-mcp-server/
- Apple WWDC26 "What's new in Xcode 27": https://developer.apple.com/videos/play/wwdc2026/258/ ;
  "Xcode, agents, and you": https://developer.apple.com/videos/play/wwdc2026/259/ ;
  WWDC25 "Record, replay, and review": https://developer.apple.com/videos/play/wwdc2025/344/
- MobileBuildMCP: https://github.com/getsentry/MobileBuildMCP (CHANGELOG, `src/mcp/tools/ui-automation/shared/`) ;
  release 2.7.1: https://github.com/getsentry/MobileBuildMCP/releases/tag/v2.7.1
- Maestro: https://github.com/mobile-dev-inc/maestro ; https://docs.maestro.dev/get-started/how-maestro-works ;
  máy thật: https://devicelab.dev/blog/maestro-ios-real-device-testing
- WebDriverAgent quiescence: https://github.com/appium/WebDriverAgent/blob/master/WebDriverAgentLib/Categories/XCUIApplicationProcess+FBQuiescence.m ;
  PR #935 (Xcode 16 signature): https://github.com/appium/WebDriverAgent/pull/935
- Appium XCUITest driver, quiescence: https://github.com/appium/appium-xcuitest-driver/pull/1290
- Apple forum "App failed to quiesce": https://developer.apple.com/forums/thread/6503?page=2
