# fastSimulatorTest, fastDeviceTest & fastCarPlayTest

Bạn chỉ cần gõ lệnh và mô tả bằng lời. Agent tự viết flow hoặc bấm từng bước, chạy, rồi báo
PASS/FAIL kèm ảnh chụp.

## Cài đặt (máy mới)

Chỉ cần có sẵn Xcode 26 hoặc 27. Không cần Homebrew hay xcodegen: AXe và baguette được khóa trong
`vendor/tools.json`, kiểm SHA-256 rồi cài local. baguette là tùy chọn cho `fastCarPlayTest`: máy
Intel hoặc đang offline vẫn cài tool bình thường và có thể chạy `./install.sh --install-baguette` sau.

**Cách nhanh nhất:** nhờ AI cài: "làm theo SETUP.md trong https://github.com/DungVC-Dev/fast-ios-device-test".
[SETUP.md](SETUP.md) có từng bước, lệnh kiểm tra, kết quả mong đợi và cách sửa từng lỗi.

Cài hai phần:

1. **Bộ chạy trên Mac** (engine, AXe, baguette tùy chọn, các lệnh `fast…`), dùng chung cho mọi agent:
   `npx fast-ios-device-test`. Bản cài thường tự bật job launchd hằng ngày và in
   `auto-update: on (daily; turn off: npx fast-ios-device-test auto-update off)`. Job tự áp dụng
   bản vá/bản minor và cập nhật plugin Codex, Claude Code, Antigravity, Gemini; bản major chỉ báo để
   người dùng chạy thủ công. Xem/tắt/bật bằng `npx fast-ios-device-test auto-update status|off|on`.
   `FAST_IOS_NO_AUTO_UPDATE=1` lúc cài sẽ không bật job; `--link` cũng không tự bật vì clone cập nhật
   bằng git. Cập nhật ngay: `npx fast-ios-device-test update`. Khi có bản mới,
   `fastSimulatorTest`/`fastDeviceTest` in một dòng `update available: …` (tối đa một lần mỗi ngày,
   tắt toàn bộ kiểm tra mạng bằng `FAST_IOS_NO_UPDATE_CHECK=1`). Job bỏ lượt nếu đang có lệnh fast*
   chạy và ghi log xoay vòng ở `~/Library/Logs/fast-ios-device-test-update.log`. Với Claude Code, lệnh này đã cài luôn
   hai skill `fast-ios-device-test`, `iphone-duo-swiftui`, các lệnh `/fastSimulatorTest`,
   `/fastDeviceTest`, `/fastCarPlayTest`, `/fastUIReview` và subagent.
   Khi sửa code cho Duo, có thể chạy `npx fast-ios-device-test xcode-skills` để xuất thêm skill
   `apple-app-resizability` từ Xcode đang cài. Nội dung Apple chỉ nằm trên máy, không có trong repo/npm.
   Cập nhật các tool như dependency đã khóa: `npx fast-ios-device-test update-tools` (hoặc
   `update-axe` / `update-baguette`); lệnh này tải release mới nhất, kiểm checksum + version,
   cập nhật pin rồi cài lại local.
2. **Skill cho agent khác** (bộ chạy ở bước 1 không cài phần này):
   - Codex: `codex plugin marketplace add DungVC-Dev/fast-ios-device-test` rồi
     `codex plugin add fast-ios-device-test@fast-ios-device-test`
   - Antigravity: `agy plugin install https://github.com/DungVC-Dev/fast-ios-device-test`
   - Gemini CLI: `gemini extensions install https://github.com/DungVC-Dev/fast-ios-device-test --auto-update`

Claude Code không cho marketplace bên thứ ba tự opt-in bằng manifest: trong `/plugin`, mở
**Marketplaces**, chọn `fast-ios-device-test`, rồi **Enable auto-update**. Codex không có công tắc
auto-update riêng; job hằng ngày của tool chạy cặp refresh/install đã kiểm chứng.

Kiểm tra: `npx fast-ios-device-test --check`, dòng cuối phải là `CHECK OK`. Lệnh này cũng báo khi
version AXe pin/local/latest không khớp; baguette thiếu/cũ chỉ được báo là tùy chọn, không làm
`CHECK OK` thất bại, đồng thời in trạng thái và kết quả gần nhất của auto-update. Lệnh cũng báo khi skill của Codex hoặc Antigravity bị hỏng (link trỏ
vào thư mục đã xoá, plugin rỗng). Sau đó thoát
rồi mở lại agent.

Dọn cache và bản build khi test (tool vẫn còn): `npx fast-ios-device-test clean --project <thư mục project> --yes` (không có `--yes` chỉ liệt kê). Gỡ tool khỏi máy: `npx fast-ios-device-test --uninstall` (cache và `build/` vẫn giữ, muốn xoá thì chạy `clean` trước).

**Tự cài (để sửa tool):**

1. Mở Terminal, chạy:
   ```bash
   git clone https://github.com/DungVC-Dev/fast-ios-device-test.git ~/fast-ios-device-test
   ~/fast-ios-device-test/install.sh --link
   ~/fast-ios-device-test/install.sh --check          # dòng cuối phải là CHECK OK
   ```
   Dùng Codex hoặc Antigravity thì link skill từ bản clone (README, mục "Development install"):
   `ln -sfn ~/fast-ios-device-test/skills/fast-ios-device-test ~/.codex/skills/fast-ios-device-test`
   hoặc `~/.gemini/config/skills/fast-ios-device-test`; làm tương tự cho thư mục
   `skills/iphone-duo-swiftui` nếu cần sửa giao diện Duo.
2. Thoát rồi mở lại agent.

Cập nhật bản mới: `git -C ~/fast-ios-device-test pull && ~/fast-ios-device-test/install.sh --link`.
Giữ nguyên thư mục `~/fast-ios-device-test` vì skill và lệnh trỏ vào đó (dời hoặc xoá thư mục thì
`--check` báo `broken link`; chạy lại `install.sh --link` từ bản clone mới). Không dùng git thì tải
zip ở trang [Releases](https://github.com/DungVC-Dev/fast-ios-device-test/releases), giải nén và chạy
`install.sh` trong đó (không thêm cờ).

## iPhone thật

Mỗi máy cần (chủ máy bật một lần):

- Mở khoá và cắm vào Mac (hoặc chung Wi‑Fi sau khi đã ghép đôi), đã bấm "Tin cậy máy tính này".
- Cài đặt › Quyền riêng tư & Bảo mật › Chế độ nhà phát triển: bật.
- Có development profile chứa máy đó: thường chỉ cần đăng nhập Xcode và chạy một app bất kỳ lên
  máy một lần. Tool không cần đăng nhập Apple ID.
- Lần đầu iOS có thể hỏi bật Cài đặt › Nhà phát triển › Enable UI Automation.

Kiểm tra một máy: `fastDeviceTest check --device <tên>`: báo thiếu gì và cách sửa. Máy bị khoá
giữa chừng thì tool báo ngay sau vài giây: mở khoá bằng tay rồi chạy lại. Đặt Tự động khoá dài hơn
(ví dụ 5 phút) trên máy test thì ít gặp hơn.

Trước mỗi flow và lệnh `do`/`serve`/`lock`, tool tự chạy preflight nhanh (một lần gọi
`devicectl`, cache ngắn theo UDID). Nếu máy chưa ghép đôi/tin cậy, mất kết nối, tắt Developer Mode,
chưa mount developer disk image, iOS mới hơn Xcode, hoặc không có development profile chứa máy,
tool dừng trước khi build/cài và chỉ in một dòng `FAIL error=<lỗi>: <cách sửa>`.
`fastDeviceTest check` vẫn là báo cáo đầy đủ. Lỗi lúc chạy cũng chỉ rõ cách xử lý: bật
Settings › Developer › Enable UI Automation; trust developer ở Settings › General › VPN & Device
Management; chờ Xcode chuẩn bị/copy shared cache; dùng Xcode khớp iOS; đặt passcode nếu Developer
Mode yêu cầu; hoặc cắm lại máy nếu bị ngắt giữa chừng.

## Lệnh

| Lệnh | Dùng khi |
| --- | --- |
| `/fastSimulatorTest <mô tả>` | Test trên Simulator (mặc định, nhanh) |
| `/fastDeviceTest <mô tả>` | Test trên iPhone thật, kể cả Settings / Shortcuts / màn hình chính |
| `/fastCarPlayTest <flow>` | Test tuần tự cả màn hình điện thoại và CarPlay; sim hoặc iPhone thật + Apple CarPlay Simulator |
| `/fastUIReview <session>` | Xem lại video đã quay |
| (tự động) | Mỗi lần chạy flow PASS, và lần `--before` fail đúng bước kiểm tra, được chép ra `~/Desktop/<project> <ticket>/`: ảnh ghép có chú thích, video nén, ảnh lẻ trong `source/`. Merge PR xong thì tự xoá folder đó |
| `fastEvidenceSheet <spec.json>` | Dựng lại ảnh ghép sau khi sửa `source/sheet.json` (đổi thứ tự, chú thích, ảnh) |
| `fastUIClean [--project <root>] [--maps] [--max-dd-gb N] [--yes]` | Liệt kê dung lượng rồi (với `--yes`) xoá cache fast UI: runner iPhone, helper, lock, session, output của project và DerivedData của repo đã mất; `--max-dd-gb N` chọn thêm cache repo ít dùng nhất vượt giới hạn. Không đụng evidence trên Desktop, bỏ qua thứ đang chạy |
| `fastUIMap <bundle id> [--find <chữ> \| --path-to <màn>]` | Bản đồ màn hình các lần chạy trước đã ghi: selector, đường đi; `--path-to` in sẵn một lệnh đi thẳng tới màn đó |
| `fastDeviceTest check --device <tên>` | Kiểm tra một iPhone trước khi chạy |
| `fastCarPlayTest doctor --target sim\|hardware` | Kiểm tra bộ CarPlay, chỉ đọc và báo cách sửa |

Agent tự chọn giữa viết flow (để chạy lại, chạy nhiều máy, quay video) và bấm từng bước bằng
`do` (để dò màn mới). Việc dò dài có thể giao cho subagent `ui-explorer` (Haiku, đang thử nghiệm).

## Ví dụ

```
/fastSimulatorTest mở tab Lyrics ở trạng thái premium, chụp màn hình
/fastSimulatorTest màn Home, chạy cả sáng và tối, có quay video
/fastSimulatorTest kiểm tra Home trên iPhone Duo ở closed, open, book và tabletop
/fastDeviceTest trên iPhone của tôi: mở Home, kiểm tra không hiện paywall
/fastDeviceTest trên iPhone, có quay video: mở paywall rồi đóng
/fastDeviceTest bấm giữ widget ngoài màn hình chính, mở Edit Widget
/fastCarPlayTest chạy flow CPR-01 trên Apple CarPlay Simulator và iPhone của tôi
```

## Cần biết

- Cử chỉ hỗ trợ: bấm, bấm giữ, chạm đúp, kéo-thả, vuốt (cả vuốt từ mép), gõ chữ, phím
  (xoá, Return, mũi tên, Cmd+…), nút Home/âm lượng, thanh trượt; riêng iPhone thêm pinch, xoay hai
  ngón, xoay ngang/dọc, bánh xe chọn giờ, chạm hai ngón. Simulator không làm được pinch, xoay,
  bánh xe; iPhone không lắc máy được: tool báo rõ thay vì làm sai.
- Thời gian: một bước `do` khoảng 2 giây trên iPhone, 3 giây trên Simulator; một flow trên
  iPhone khoảng 7 giây khi runner đang chạy (lần đầu ~15–20 giây).
- Runner trên iPhone tự tắt sau 5 phút rảnh; agent luôn `stop` khi xong. Xong hẳn việc thì agent
  chạy `fastDeviceTest lock` (tắt runner rồi khoá màn hình, cho máy để Auto-Lock "Never") và
  `fastSimulatorTest shutdown` (tắt các Simulator đang bật cho nhẹ máy). Máy đang bị người khác
  dùng thì tool báo "busy", không giành máy.
- Nhiều bước gộp một lệnh mà có bước nguy hiểm (Xoá, Thanh toán, Gửi, Đăng xuất…) thì tool từ chối,
  trừ khi agent ghi rõ `"confirm": true`.
- Trạng thái cài sẵn (premium, đã xong onboarding…) tự bị xoá sau khi test trên Simulator; trên
  iPhone, chúng chỉ là tham số khi mở app, không ghi vào máy.
- Quay video được cả Simulator lẫn iPhone thật (iPhone dùng tính năng quay của XCTest, không cần
  Control Center hay QuickTime); video nén nhẹ, khoảng 1–2 MB cho 20 giây.
- iPhone Duo cần Xcode 27.1. Flow dùng
  `{"type":"duo","pose":"closed|open|book|tabletop","orientation":"portrait|landscape"}`
  để đổi màn hình/tư thế/hướng; `orientation` là tuỳ chọn. `closed`/`open` dùng được cả hai hướng;
  `book` chỉ landscape (nếp dọc), `tabletop` chỉ portrait (nếp ngang).
  `screenshot` có thể ghi `"display":"outer"` hoặc `"inner"`.
  Chạy matrix bằng `--duo-pose` và chỉ thêm `--duo-orientation` khi cần biến thể hướng; hướng
  không mặc định có hậu tố như `@duo-closed-landscape`. Video quay đúng framebuffer.
  Khi sửa SwiftUI, dùng skill `iphone-duo-swiftui`; nếu đã export thì dùng thêm
  `apple-app-resizability` của Xcode.
- CarPlay Simulator.app cần Xcode 26.6, mặc định iOS 26.5 và simulator riêng tên `agent-tmp-*`.
  Nếu thiếu `baguette`, chạy `./install.sh --install-baguette`.
  Dùng `--display widescreen` hoặc `--display standard` cho 1920×720@2 hoặc 800×480@2. Mỗi lệnh
  chỉ chạy một cỡ vì đổi cỡ phải reboot simulator; chỉ chạy cỡ thứ hai khi người dùng yêu cầu.
  Khi đổi cỡ, tool thoát Simulator.app để xoá mode CarPlay đang cache rồi chỉ reboot máy
  `agent-tmp-*`; nếu còn cửa sổ Simulator không thuộc agent thì tool dừng để không đụng máy người dùng.
  Không bao giờ dùng
  `simctl io screenshot --display external` vì trên iOS 27 lệnh đó làm restart CarPlay.
  `--record` chỉ dùng với Apple CarPlay Simulator + iPhone thật; target `sim` dùng các bước
  `car_screenshot` vì tool chủ động từ chối quay nhầm cửa sổ.
- Bàn phím tiếng Việt (Telex) trên máy sẽ biến chữ agent gõ; số và phím thì không sao.

Có gì mới: xem [CHANGELOG.md](CHANGELOG.md).
