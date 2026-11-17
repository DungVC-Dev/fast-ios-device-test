# /testAmplitude

Gửi file tracking plan (xlsx) cho Claude, Claude tự kiểm tra event Amplitude của app và trả bảng PASS/FAIL kèm bằng chứng.

## Cài đặt (một lần)

`/testAmplitude` cài cùng fast-ios-device-test (`npx fast-ios-device-test`, hoặc `./install.sh` trong bản clone). Cần thêm hai thư viện Python:

```bash
python3 -m pip install --user openpyxl pillow
```

Thoát rồi mở lại Claude Code.

## Cách dùng

```
/testAmplitude ~/Downloads/<App> - Amplitude Events and Properties.xlsx
/testAmplitude <file xlsx> chỉ nhóm Onboarding
/testAmplitude <file xlsx> event Home Screen Viewed, Settings Opened
```

Claude sẽ:
1. So doc với code (vài giây): event thiếu, event thừa, sai tên property.
2. Tự bấm app trên Simulator (hoặc iPhone cắm cáp vào Mac) theo từng hành trình và ghi lại event app bắn ra.
3. Trả bảng: PASS / FAIL / MISSING / DUPLICATE / UNPLANNED, kèm payload thật.

## Cần biết

- Chỉ test được event bắn từ app. Event từ backend, mua hàng thật, đăng nhập Apple/Google thật cần kiểm tra trên Amplitude.
- Muốn Claude xác nhận event đã lên Amplitude: cài Amplitude MCP một lần, xem `skills/amplitude-tracking-test/references/amplitude-mcp.md` (thư mục gốc của tool). Claude chỉ đọc dữ liệu tracking trên Amplitude, không tạo/sửa/xoá gì (taxonomy, chart, dashboard...); nên đăng nhập bằng tài khoản quyền Viewer trên project Staging.
- Tool tự từ chối nếu bản build đang gửi về project Amplitude production.
- Test trên máy thật: chỉ dùng iPhone cắm cáp vào Mac (máy Wi-Fi bị từ chối), mở khoá máy, đã cài sẵn app. Ví dụ: `/testAmplitude <file xlsx> trên máy thật, nhóm Onboarding`.
- Runner iPhone của /testAmplitude có cache, cổng và bundle id riêng, không đụng runner của `fastDeviceTest`. Dù vậy, đừng chạy cả hai trên cùng một iPhone cùng lúc.
- Gói này không kèm flow của app nào. Flow bạn lưu lại nằm ở thư mục bạn chọn, không nằm trong gói.
