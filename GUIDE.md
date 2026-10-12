# fastSimulatorTest & fastDeviceTest

Bạn chỉ cần gõ lệnh và mô tả bằng lời. Agent tự viết flow, chạy, rồi báo PASS/FAIL kèm ảnh chụp.

## Cài đặt (máy mới)

Chỉ cần có sẵn Xcode. Không cần Homebrew, không cần xcodegen: AXe đã đóng kèm trong gói.

1. Tải file `fast-ios-device-test-<version>.zip` về, giải nén (ví dụ vào `~/Downloads`).
2. Mở Terminal, chạy:
   ```bash
   ~/Downloads/fast-ios-device-test/install.sh
   ```
   Cài xong trong vài giây. Kiểm tra lại bất cứ lúc nào bằng `install.sh --check`.
3. Thoát rồi mở lại Claude Code.

Sau khi cài xong có thể xoá file zip và thư mục giải nén. Muốn cập nhật bản mới thì làm lại 3 bước trên.
Lần chạy đầu trong mỗi dự án mất thêm 1–2 phút vì phải boot simulator và build app; từ lần hai mỗi flow chỉ 6–12 giây.

Người gửi tạo file zip bằng lệnh `bash make-zip.sh` trong thư mục cha của tool.

## Lệnh

| Lệnh | Dùng khi |
| --- | --- |
| `/fastSimulatorTest <mô tả>` | Test trên Simulator (mặc định, nhanh) |
| `/fastDeviceTest <mô tả>` | Test trên iPhone thật, kể cả Settings / Shortcuts |
| `/fastUIReview <session>` | Xem lại video đã quay |

## Ví dụ

```
/fastSimulatorTest mở tab Lyrics ở trạng thái premium, chụp màn hình
/fastSimulatorTest màn Home, chạy cả sáng và tối, có quay video
/fastDeviceTest trên iPhone của tôi: mở Home, kiểm tra không hiện paywall
```

## Cần biết

- Trạng thái cài sẵn (premium, đã xong onboarding…) tự bị xoá sau khi test, không cần dọn tay.
- Muốn test trên máy thật thì máy phải được mở khoá và cắm vào Mac. Không cần đăng nhập Apple ID.
- Thời gian mỗi lần test: simulator khoảng 12 giây, máy thật khoảng 8–13 giây.
