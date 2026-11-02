# fastSimulatorTest & fastDeviceTest

Bạn chỉ cần gõ lệnh và mô tả bằng lời. Agent tự viết flow hoặc bấm từng bước, chạy, rồi báo
PASS/FAIL kèm ảnh chụp.

## Cài đặt (máy mới)

Chỉ cần có sẵn Xcode 26 hoặc 27. Không cần Homebrew hay xcodegen: phiên bản AXe được khóa trong
`vendor/axe.json`, kiểm SHA-256 rồi cài local từ tarball đóng kèm.

**Cách nhanh nhất:** nhờ AI cài: "làm theo SETUP.md trong https://github.com/DungVC-Dev/fast-ios-device-test".
[SETUP.md](SETUP.md) có từng bước, lệnh kiểm tra, kết quả mong đợi và cách sửa từng lỗi.

Cài hai phần:

1. **Bộ chạy trên Mac** (engine, AXe, các lệnh `fast…`), dùng chung cho mọi agent:
   `npx fast-ios-device-test`. Cập nhật: `npx fast-ios-device-test update` (cập nhật luôn plugin
   Codex và Claude Code; Antigravity và Gemini thì in ra lệnh cần chạy). Khi có bản mới,
   `fastSimulatorTest`/`fastDeviceTest` in một dòng `update available: …` (tối đa một lần mỗi ngày,
   không tự cài; tắt bằng `FAST_IOS_NO_UPDATE_CHECK=1`). Với Claude Code, lệnh này đã cài luôn
   skill, các lệnh `/fastSimulatorTest`, `/fastDeviceTest`, `/fastUIReview` và subagent.
   Cập nhật riêng AXe như một dependency đã khóa: `npx fast-ios-device-test update-axe`; lệnh này
   tải release AXe mới nhất, chạy kiểm tra version, cập nhật pin + tarball offline rồi cài lại local.
2. **Skill cho agent khác** (bộ chạy ở bước 1 không cài phần này):
   - Codex: `codex plugin marketplace add DungVC-Dev/fast-ios-device-test` rồi
     `codex plugin add fast-ios-device-test@fast-ios-device-test`
   - Antigravity: `agy plugin install https://github.com/DungVC-Dev/fast-ios-device-test`
   - Gemini CLI: `gemini extensions install https://github.com/DungVC-Dev/fast-ios-device-test`

Kiểm tra: `npx fast-ios-device-test --check`, dòng cuối phải là `CHECK OK`. Lệnh này cũng báo khi
version AXe pin/local/latest không khớp và khi skill của Codex hoặc Antigravity bị hỏng (link trỏ
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
   hoặc `~/.gemini/config/skills/fast-ios-device-test`.
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

## Lệnh

| Lệnh | Dùng khi |
| --- | --- |
| `/fastSimulatorTest <mô tả>` | Test trên Simulator (mặc định, nhanh) |
| `/fastDeviceTest <mô tả>` | Test trên iPhone thật, kể cả Settings / Shortcuts / màn hình chính |
| `/fastUIReview <session>` | Xem lại video đã quay |
| (tự động) | Mỗi lần chạy flow PASS, và lần `--before` fail đúng bước kiểm tra, được chép ra `~/Desktop/<project> <ticket>/`: ảnh ghép có chú thích, video nén, ảnh lẻ trong `source/`. Merge PR xong thì tự xoá folder đó |
| `fastEvidenceSheet <spec.json>` | Dựng lại ảnh ghép sau khi sửa `source/sheet.json` (đổi thứ tự, chú thích, ảnh) |
| `fastUIClean [--project <root>] [--maps] [--yes]` | Liệt kê rồi (với `--yes`) xoá cache fast UI để lại: runner iPhone, helper, lock, session, `build/fast-ui` của project; bản đồ màn hình chỉ khi có `--maps`. Không đụng evidence trên Desktop, bỏ qua thứ đang chạy |
| `fastUIMap <bundle id> [--find <chữ> \| --path-to <màn>]` | Bản đồ màn hình các lần chạy trước đã ghi: selector, đường đi; `--path-to` in sẵn một lệnh đi thẳng tới màn đó |
| `fastDeviceTest check --device <tên>` | Kiểm tra một iPhone trước khi chạy |

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
- iPhone Duo cần Xcode 27.1. Flow dùng `{"type":"duo","pose":"closed|open|book|tabletop"}`
  để đổi màn hình/tư thế; `screenshot` có thể ghi `"display":"outer"` hoặc `"inner"`.
  Chạy matrix bằng `--duo-pose`; mỗi dòng có hậu tố `@duo-<pose>` và video quay đúng framebuffer.
- Bàn phím tiếng Việt (Telex) trên máy sẽ biến chữ agent gõ; số và phím thì không sao.

Có gì mới: xem [CHANGELOG.md](CHANGELOG.md).
