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
- Khi không lấy được bounds cửa sổ, capture hiện có thể chụp monitor chính trên Windows/X11 hoặc toàn output Wayland; metadata vẫn ghi `selected-window crop`. Không nên xem giới hạn crop là bảo đảm trong mọi trường hợp cho tới khi xử lý fail-closed.
- Trên Linux, nếu không tìm thấy cửa sổ có trạng thái AT-SPI `ACTIVE`, backend hiện lấy cửa sổ đầu tiên trong danh sách. Thứ tự đó không đảm bảo là foreground.
- Windows UIA lấy danh sách `children()` trước khi cắt theo ngân sách node; ứng dụng có container rất rộng vẫn có thể tốn thời gian/bộ nhớ vượt kỳ vọng của `max_nodes`.
- Windows click fallback sang `click_input()` khi `invoke()` ném bất kỳ exception nào. Chưa có bước xác minh target vẫn visible/đúng bounds ngay trước input hoặc xác minh trạng thái sau action.
- Whitelist role dùng để bỏ tên trường nhập là heuristic theo role phổ biến, không phải lớp DLP tổng quát; ứng dụng tùy biến có thể công bố role khác.

## 7. Lịch sử Git liên quan

- `1cee6e3`: snapshot repo ban đầu.
- `059198b`: prototype MCP server Windows C#.
- `06e560a`: migration sang Python MCP đa nền tảng, source, tests, README và cấu hình hiện tại.
- `94eb42e`: làm rõ cây source trong README và thêm báo cáo triển khai.

Báo cáo này mô tả phạm vi đã triển khai; các mục trong phần giới hạn là hướng phát triển tiếp theo, không được xem là tính năng đã hoàn thành.

## 8. Đánh giá mức sẵn sàng sử dụng thực tế

### Kết luận ngắn

AncharView hiện là **prototype kỹ thuật có thể thử nghiệm có giám sát**, chưa nên xem là agent điều khiển desktop production hoặc chạy không giám sát. Windows đã qua smoke test đọc UIA và MCP; chưa có end-to-end test thao tác ứng dụng. Linux mới được rà code, chưa chạy trên desktop Linux thật. Quan trọng nhất, chế độ tự đính kèm vision có thể gửi phạm vi rộng hơn cửa sổ được chọn khi không lấy được bounds.

### Phát hiện ưu tiên cao

1. **Phạm vi ảnh có thể rộng hơn metadata báo.** `DesktopBackend.capture()` dùng monitor chính nếu `window.bounds` không có; nhánh Wayland gọi `grim` không có geometry cũng chụp toàn output. `observe_screen` vẫn khai báo `scope="selected-window crop"`. Vì `auto` có thể tự yêu cầu ảnh khi accessibility yếu, đây vừa là rủi ro riêng tư vừa làm agent hiểu sai phạm vi quan sát. Trước khi dùng trên màn hình nhạy cảm, cần fail closed nếu không xác định được vùng cửa sổ, hoặc trả rõ `scope=display` và yêu cầu opt-in riêng.
2. **Foreground Linux chưa xác định chắc chắn.** Nếu AT-SPI không đánh dấu `ACTIVE`, `foreground_window()` chọn `windows[0]`. Agent có thể hành động trên nhầm app mà không biết. Nên trả lỗi “không xác định được foreground” hoặc dùng nguồn focus đáng tin hơn thay vì đoán.
3. **Fallback click Windows thiếu xác minh.** Mọi lỗi từ `invoke()` đều dẫn tới `click_input()`. Lỗi do phần tử stale hoặc UI đổi có thể tạo input tọa độ không còn trỏ vào target ban đầu. Cần kiểm tra ID còn hợp lệ, visibility/bounds và cửa sổ sở hữu target trước fallback; trả lỗi nếu không xác minh được.
4. **Chưa có guard cho hành động rủi ro cao.** `click_element` có thể nhấn Send/Delete/Pay giống như nút thông thường; chưa có allowlist, consent hay audit log. Chỉ dùng với người giám sát cho tới khi có chính sách xác nhận hành động không thể đảo ngược.

### Phát hiện ưu tiên tiếp theo

- `max_nodes` giới hạn số node được xếp vào kết quả, nhưng trên Windows `wrapper.children()` tạo danh sách con trước khi cắt; giao diện có container rất rộng vẫn có thể chậm hoặc tốn bộ nhớ.
- Matching task và chọn vision dựa trên chuỗi từ khóa. Từ đồng nghĩa, ngôn ngữ khác, mục tiêu mơ hồ và substring trùng có thể làm chọn sai node hoặc bật/tắt ảnh không như mong muốn.
- Test hiện tập trung vào policy thuần. Chưa có test backend giả lập cho stale element, cửa sổ không active, thiếu bounds, lỗi chụp, disabled control, hay kết quả action; chưa có regression test UIA thật.
- `pyproject.toml` khai báo extra Linux `pyautogui`, nhưng adapter hiện tại không dùng nó. Cần bỏ dependency gây kỳ vọng sai hoặc triển khai rõ input fallback với quyền/giới hạn riêng.
- VS Code MCP config mặc định là đường dẫn virtualenv Windows; Linux phải chỉnh thủ công. Cần kiểm chứng quy trình cài sạch trên từng nền tảng và giảm cấu hình thủ công nếu muốn phân phối rộng.

## 9. Lộ trình thực dụng

### P0: bảo vệ desktop và dữ liệu

- Không chụp toàn màn hình ngầm khi mục tiêu là crop cửa sổ. Nếu bounds thiếu, báo lỗi hoặc yêu cầu agent/user bật capture toàn display một cách tường minh.
- Không đoán foreground Linux. Báo trạng thái không xác định để agent hỏi lại hoặc yêu cầu chọn `window_id`.
- Trước coordinate fallback, xác minh element còn visible, bounds hợp lệ, cửa sổ vẫn đúng; sau action trả method và kết quả xác minh, không chỉ thông báo đã gửi input.
- Thêm guard/consent cho nút và action có khả năng gửi, xóa, mua hoặc thay đổi dữ liệu không thể hoàn tác; log action ở local với dữ liệu nhạy cảm đã loại bỏ.

### P1: chứng minh dùng được trên hai nền tảng

- Tạo test backend giả lập cho thiếu bounds, không có active window, cây rỗng, stale IDs, node cap, action lỗi và redaction.
- Chạy checklist thủ công trên Windows 10/11 và Linux GNOME/X11; sau đó kiểm tra Wayland riêng với quyền capture thực tế.
- Dùng app thử nghiệm không nhạy cảm (ví dụ Notepad/text editor) để xác minh list → observe → click → set_text; xác nhận không đọc lại nội dung nhập và ảnh đúng vùng.
- Đo thời gian và kích thước kết quả trên UI nhỏ, UI nhiều node và app custom-rendered để chọn mặc định `max_nodes` có cơ sở.

### P2: tăng độ chính xác và trải nghiệm agent

- Cải thiện relevance với role/action aliases đa ngôn ngữ, token budget thực tế và lý do chọn/bỏ node.
- Cân nhắc browser DOM/CDP như adapter riêng, chỉ bật khi người dùng cấp quyền; thêm OCR/crop vision cho UI không có accessibility nếu cần.
- Thêm event/diff, `find_elements`, scroll, wait-for và action confirmation sau khi đường cơ sở hai hệ điều hành ổn định.
- Cung cấp cấu hình MCP/cài đặt dễ chọn Windows/Linux và kiểm thử clean-install trong CI phù hợp từng OS.

### Cách dùng thử hiện tại

Chỉ thử trên desktop không nhạy cảm và có người theo dõi. Trên Windows, ưu tiên task đọc hoặc thao tác có thể đảo ngược; đặt `visual_mode="never"` khi không cần ảnh cho tới khi P0 về bounds được xử lý. Không bật agent tự hành cho gửi/xóa/thanh toán. Trên Linux, coi backend là chưa xác nhận cho tới khi chạy checklist AT-SPI trên desktop thật.

Đánh giá này là code review theo source hiện tại, không phải chứng nhận an toàn hoặc kết quả kiểm thử Linux. Các mục P0/P1 cần được xử lý và kiểm tra trước khi giới thiệu AncharView là công cụ điều khiển desktop dùng production.
