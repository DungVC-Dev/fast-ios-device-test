# fastSimulatorTest & fastDeviceTest

Bạn chỉ cần gõ lệnh và mô tả bằng lời. Agent tự viết flow, chạy, rồi báo PASS/FAIL kèm ảnh chụp.

## Cài đặt (máy mới)

Chỉ cần có sẵn Xcode. Không cần Homebrew, không cần xcodegen: AXe đã đóng kèm trong gói.

1. Mở Terminal, chạy:
   ```bash
   git clone https://github.com/kiluss2/fast-ios-device-test.git ~/fast-ios-device-test
   ~/fast-ios-device-test/install.sh --link
   ```
   Cài xong trong vài giây. Kiểm tra lại bất cứ lúc nào bằng `install.sh --check`.
2. Thoát rồi mở lại Claude Code.

Cập nhật bản mới: `git -C ~/fast-ios-device-test pull`. Giữ nguyên thư mục `~/fast-ios-device-test`
vì skill và lệnh trỏ vào đó.

Không dùng git: tải `fast-ios-device-test-<version>.zip` ở trang
[Releases](https://github.com/kiluss2/fast-ios-device-test/releases), giải nén ở đâu cũng được,
chạy `install.sh` trong đó (không thêm cờ). Cách này chép tool vào `~/.local/share`, nên xoá
thư mục giải nén sau đó cũng không sao.

Lần chạy đầu trong mỗi dự án mất thêm 1–2 phút vì phải boot simulator và build app; từ lần hai
mỗi flow chỉ 6–12 giây. Có gì mới: xem [CHANGELOG.md](CHANGELOG.md).

## Lệnh

| Lệnh | Dùng khi |
| --- | --- |
| `/fastSimulatorTest <mô tả>` | Test trên Simulator (mặc định, nhanh) |
| `/fastDeviceTest <mô tả>` | Test trên iPhone thật, kể cả Settings / Shortcuts |
| `/fastUIReview <session>` | Xem lại video đã quay |
| `fastEvidenceSheet <spec.json>` | Ghép ảnh chụp thành một ảnh có chú thích để đính kèm PR (agent tự viết spec) |
| `fastUIMap <bundle id> [--find <chữ>]` | Xem bản đồ màn hình app mà các lần chạy trước đã ghi lại (selector, đường đi) |

## Ví dụ

```
/fastSimulatorTest mở tab Lyrics ở trạng thái premium, chụp màn hình
/fastSimulatorTest màn Home, chạy cả sáng và tối, có quay video
/fastDeviceTest trên iPhone của tôi: mở Home, kiểm tra không hiện paywall
/fastDeviceTest trên iPhone, có quay video: mở paywall rồi đóng
```

## Cần biết

- Trạng thái cài sẵn (premium, đã xong onboarding…) tự bị xoá sau khi test, không cần dọn tay.
- Muốn test trên máy thật thì máy phải được mở khoá và cắm vào Mac. Không cần đăng nhập Apple ID.
- Thời gian mỗi lần test: simulator khoảng 12 giây, máy thật khoảng 8–13 giây.
- Quay video được cả Simulator lẫn iPhone thật (iPhone dùng tính năng quay màn hình có sẵn của
  XCTest, không cần Control Center hay QuickTime). Video được nén nhẹ để xem review: khoảng
  1–2 MB cho 20 giây.
