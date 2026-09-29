# Báo cáo triển khai AncharView

## 1. Mục tiêu

Xây dựng một MCP server chạy cục bộ để Agent có thể quan sát và thao tác giao diện máy tính. Hệ thống ưu tiên dữ liệu accessibility có cấu trúc để giảm token và độ trễ, nhưng vẫn giữ vision để xử lý nội dung mà cây accessibility không mô tả được. Phạm vi nền tảng hiện tại là Windows 10+ và Linux.

## 2. Quá trình và quyết định kiến trúc

### Prototype Windows bằng C#

Ban đầu dự án có prototype MCP server C# trên Windows, sử dụng UI Automation trực tiếp. Cách này phù hợp để thử UIA và MCP trên Windows, nhưng không đáp ứng mục tiêu Linux nếu tiếp tục để toàn bộ giao diện phụ thuộc vào API Windows.

### Chuyển sang Python và adapter theo hệ điều hành

Workspace sau đó đã bắt đầu chuyển sang Python. Tiếp tục chuyển đổi này giúp đặt giao thức MCP, chính sách context và các hợp đồng backend trong một lớp dùng chung, đồng thời tách API riêng của từng hệ điều hành:

- Windows: UI Automation thông qua `pywinauto`.
- Linux: AT-SPI thông qua binding `pyatspi` do hệ điều hành cung cấp.
- Ảnh: `mss` trên Windows/X11; `grim` cho vùng ảnh trên Wayland khi có sẵn và được compositor cho phép.

Các file C# trong `src/AncharView.Server/` được loại khỏi Git vì đã được thay thế. Các thư mục `bin/` và `obj/` còn sót lại cục bộ chỉ là kết quả build cũ, không phải mã nguồn. Source Python thực tế đều được theo dõi trong `src/ancharview/`.

## 3. Thành phần đã triển khai

### MCP server và công cụ

MCP server dùng Python SDK chính thức và stdio. Đăng ký trong `.vscode/mcp.json` trỏ đến Python virtualenv trên Windows; README chỉ cách đổi sang đường dẫn virtualenv Linux.

Các tool được cung cấp:

- `list_windows`: liệt kê cửa sổ nhìn thấy và ID để chọn cửa sổ.
- `observe_screen`: quan sát cửa sổ foreground mặc định hoặc cửa sổ được chọn; nhận `task_goal`, `visual_mode`, `detail` và `max_nodes`.
- `capture_screen`: chụp ảnh cửa sổ được chọn khi Agent yêu cầu rõ.
- `click_element`: kích hoạt phần tử accessibility theo ID từ lần quan sát gần nhất.
- `set_text`: đặt text qua giao diện accessibility mà không đọc giá trị kết quả trở lại.

### Context theo nhu cầu Agent

`observe_screen` xếp hạng node theo từ khóa của `task_goal`, rồi chọn lượng context theo `detail`:

- `minimal`: node đang focus và node khớp mục tiêu.
- `interactive`: node khớp mục tiêu; nếu không khớp thì ưu tiên phần tử tương tác. Giữ thêm ancestor để Agent hiểu cấu trúc cha–con.
- `full`: cây accessibility đã giới hạn bởi `max_nodes`.

Kết quả nêu số node đã kiểm tra, số node được trả, trạng thái lọc và việc cây có bị cắt hay không. Đây là xếp hạng từ khóa có quy tắc, chưa phải mô hình hiểu ngữ nghĩa hoặc bộ ước lượng token chính xác.

### Vision có điều kiện

`visual_mode=auto` đính kèm ảnh khi mục tiêu nhắc tới thông tin thị giác (như màu sắc, bố cục, biểu đồ, ảnh) hoặc cây accessibility có độ phủ thấp. `always` buộc gửi ảnh; `never` tắt ảnh trong lần quan sát đó. Ảnh chụp được giới hạn theo cửa sổ, không tự chụp nền. MCP trả ảnh dưới dạng image content, không nhúng ảnh vào chuỗi JSON.

### Giới hạn và bảo vệ dữ liệu

- Duyệt cây accessibility có giới hạn số node và độ sâu.
- ID phần tử là process-local, tối đa 8.000 phần tử cache và hết hạn sau hai phút.
- Không chủ động đọc lại giá trị ô nhập. Tên của các role nhập liệu phổ biến được bỏ trước khi đưa vào context, với danh sách riêng cho Windows và Linux.
- Không chụp màn hình trong nền và không gửi hình hoặc dữ liệu tới dịch vụ cloud từ server.
- Trên Windows, click dùng action UIA trước rồi mới fallback sang input tại vị trí phần tử.
- Trên Linux, click và nhập text chỉ hoạt động khi ứng dụng cung cấp AT-SPI action hoặc EditableText; không giả định input tọa độ luôn được hỗ trợ.

## 4. Tệp trong repo

- `src/ancharview/server.py`: đăng ký MCP tools, xếp hạng task, chọn context và chính sách vision.
- `src/ancharview/desktop.py`: hợp đồng backend, cache ID, Windows UIA, Linux AT-SPI và capture ảnh.
- `src/ancharview/__main__.py`, `src/ancharview/__init__.py`: entry point và package.
- `tests/test_vision_policy.py`: test chính sách vision, lọc context, giữ ancestor/focus và phân loại role trường nhập.
- `pyproject.toml`: package, dependencies và extras theo nền tảng.
- `.vscode/mcp.json`: đăng ký MCP server trong VS Code.
- `.github/copilot-instructions.md`: các nguyên tắc phát triển và giới hạn nền tảng.
- `README.md`: cài đặt, cấu hình, lệnh chạy, nền tảng và cây source.

`.gitignore` bỏ qua `.venv`, `__pycache__`, `*.egg-info`, cùng `bin/` và `obj/`. Vì vậy các file generated dưới `src/AncharView.Server/bin` hoặc `obj` không được upload; source cần thiết không bị bỏ sót.

## 5. Kiểm tra đã chạy

- `pytest -q`: 10 test đạt.
- `compileall`: source và test Python biên dịch cú pháp thành công.
- MCP stdio smoke test: initialize và tools/list thành công; client thấy đủ năm tool và schema `detail` có `minimal`, `interactive`, `full`.
- Windows runtime smoke test: UIA đọc được 30 node của cửa sổ foreground với giới hạn node; không chụp ảnh hoặc gửi input trong bước xác minh đó.
- `git diff --check`: không phát hiện whitespace errors.

## 6. Giới hạn hiện tại và việc chưa làm

- Chỉ xác minh runtime trên Windows trong môi trường hiện có. Linux adapter chưa được chạy trên desktop Linux thật; kết quả phụ thuộc AT-SPI, desktop environment và quyền Wayland.
- Vision hiện là chụp ảnh cửa sổ theo yêu cầu/chính sách. OCR, computer vision để xác định phần tử trên ảnh và hành động theo pixel chưa được triển khai.
- Chưa có adapter Chrome DevTools Protocol/DOM, hệ thống event/diff UI, `find_elements`, scroll, focus-window, wait-for, clipboard, allowlist ứng dụng hoặc bước xác nhận action nguy hiểm.
- Quyết định gửi ảnh và mức relevance hiện dựa trên từ khóa/độ phủ accessibility; có thể cần tinh chỉnh với agent và ứng dụng thực tế.
- Một số ứng dụng canvas/custom-rendered, remote desktop hoặc chạy quyền cao có thể không công bố đủ UIA/AT-SPI. Wayland có thể từ chối capture nếu compositor hoặc công cụ chụp không cho phép.

## 7. Lịch sử Git liên quan

- `1cee6e3`: snapshot repo ban đầu.
- `059198b`: prototype MCP server Windows C#.
- `06e560a`: migration sang Python MCP đa nền tảng, source, tests, README và cấu hình hiện tại.

Báo cáo này mô tả phạm vi đã triển khai; các mục trong phần giới hạn là hướng phát triển tiếp theo, không được xem là tính năng đã hoàn thành.
