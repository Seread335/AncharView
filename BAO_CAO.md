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
- `click_element`: xin consent qua MCP elicitation, ghi audit rồi kích hoạt phần tử accessibility theo ID từ lần quan sát gần nhất.
- `set_text`: xin consent, ghi audit rồi đặt text qua accessibility mà không đọc giá trị kết quả trở lại.

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
- `click_element` và `set_text` yêu cầu client xử lý MCP elicitation; nếu client không hỗ trợ, hủy hoặc từ chối thì server chặn action.
- Audit JSONL cục bộ ghi timestamp, action, element ID ngắn hạn, trạng thái request/consent/kết quả; không ghi text, ảnh hoặc window title. POSIX giới hạn quyền thư mục/file; Windows kế thừa ACL từ hồ sơ người dùng.
- Consent là client-mediated: server chặn client không khai báo MCP form elicitation, nhưng giao thức không chứng minh người thật đã nhấn duyệt vì một Agent/client policy có thể tự trả lời. Prompt có role/tên control đã lọc và hiển thị chính xác JSON-escaped value của `set_text`; host nhận giá trị này và có thể giữ lại, còn audit local không ghi nó.
- Khi dùng trong VS Code, cấu hình **Chat: Manage Tool Approval** để không pre-approve `click_element`/`set_text`; có thể đặt hai tool này thành `false` trong `chat.tools.eligibleForAutoApproval`. Không dùng Allow all/Autopilot cho desktop actions.
- Trên Windows, click dùng action UIA trước rồi mới fallback sang input tại vị trí phần tử.
- Trên Linux, click và nhập text chỉ hoạt động khi ứng dụng cung cấp AT-SPI action hoặc EditableText; không giả định input tọa độ luôn được hỗ trợ.

## 4. Tệp trong repo

- `src/ancharview/server.py`: đăng ký MCP tools, xếp hạng task, chọn context và chính sách vision.
- `src/ancharview/desktop.py`: hợp đồng backend, cache ID, Windows UIA, Linux AT-SPI và capture ảnh.
- `src/ancharview/audit.py`: audit JSONL tối thiểu và quyền file local.
- `src/ancharview/__main__.py`, `src/ancharview/__init__.py`: entry point và package.
- `tests/test_vision_policy.py`: test chính sách vision, lọc context, giữ ancestor/focus và phân loại role trường nhập.
- `tests/test_action_safety.py`: test consent accept/decline/unsupported, fail-closed và không ghi text vào audit.
- `pyproject.toml`: package, dependencies và extras theo nền tảng.
- `LICENSE`: toàn văn Apache License 2.0; `pyproject.toml` khai báo SPDX `Apache-2.0` để metadata package nhận diện được giấy phép.
- `.vscode/mcp.json`: đăng ký MCP server trong VS Code.
- `.github/copilot-instructions.md`: các nguyên tắc phát triển và giới hạn nền tảng.
- `README.md`: cài đặt, cấu hình, lệnh chạy, nền tảng và cây source.

`.gitignore` bỏ qua `.venv`, `__pycache__`, `*.egg-info`, cùng `bin/` và `obj/`. Vì vậy các file generated dưới `src/AncharView.Server/bin` hoặc `obj` không được upload; source cần thiết không bị bỏ sót.

## 5. Kiểm tra đã chạy

- `pytest -q`: 10 test đạt.
- Sau đợt hardening P0: `pytest -q` đạt 18 test; bổ sung kiểm tra thiếu bounds, foreground Linux mơ hồ và điều kiện coordinate fallback.
- Sau khi thêm consent/audit: `pytest -q` đạt 22 test; test consent accept/decline/client thiếu form capability, xác nhận exact `set_text` preview hiện trong consent và không xuất hiện trong audit.
- `compileall`: source và test Python biên dịch cú pháp thành công.
- MCP stdio smoke test: initialize và tools/list thành công; client thấy đủ năm tool và schema `detail` có `minimal`, `interactive`, `full`.
- MCP form-capability smoke test: initialize với `elicitation.form` và tools/list thành công; `click_element`/`set_text` được đánh dấu destructive, `Context` không lộ trong schema.
- Thử round-trip decline qua MCP SDK client chưa tới consent: client liệt kê bốn cửa sổ nhưng không cửa sổ nào trả accessibility node trong phiên test; script dừng trước `click_element`, không gửi input. Cần lặp lại trong VS Code phiên desktop có node UIA.
- Kiểm tra bundle Copilot cài local thấy các code path `elicitation/create` và form elicitation; đây không phải kiểm thử GUI/runtime và không xác nhận session hiện tại đang bật manual approval.
- Windows runtime smoke test: UIA đọc được 30 node của cửa sổ foreground với giới hạn node; không chụp ảnh hoặc gửi input trong bước xác minh đó.
- `git diff --check`: không phát hiện whitespace errors.

## 6. Giới hạn hiện tại và việc chưa làm

- Chỉ xác minh runtime trên Windows trong môi trường hiện có. Linux adapter chưa được chạy trên desktop Linux thật; kết quả phụ thuộc AT-SPI, desktop environment và quyền Wayland.
- Vision hiện là chụp ảnh cửa sổ theo yêu cầu/chính sách. OCR, computer vision để xác định phần tử trên ảnh và hành động theo pixel chưa được triển khai.
- Chưa có adapter Chrome DevTools Protocol/DOM, hệ thống event/diff UI, `find_elements`, scroll, focus-window, wait-for, clipboard hoặc allowlist ứng dụng.
- Quyết định gửi ảnh và mức relevance hiện dựa trên từ khóa/độ phủ accessibility; có thể cần tinh chỉnh với agent và ứng dụng thực tế.
- Một số ứng dụng canvas/custom-rendered, remote desktop hoặc chạy quyền cao có thể không công bố đủ UIA/AT-SPI. Wayland có thể từ chối capture nếu compositor hoặc công cụ chụp không cho phép.
- **Đã xử lý:** capture từ chối khi thiếu bounds hoặc bounds không hợp lệ; không còn fallback sang monitor/toàn output. Khi capture bị từ chối, `observe_screen` trả lỗi vision thay vì ảnh ngoài vùng đã chọn.
- **Đã xử lý:** Linux chỉ nhận foreground khi AT-SPI xác định đúng một cửa sổ `ACTIVE`; trường hợp 0 hoặc nhiều cửa sổ active yêu cầu Agent truyền `window_id` tường minh.
- Windows UIA vẫn materialize `children()` trước khi cắt theo ngân sách node; ứng dụng có container rất rộng vẫn có thể tốn thời gian/bộ nhớ vượt kỳ vọng của `max_nodes`.
- **Giảm rủi ro, chưa triệt để:** trước coordinate fallback, Windows kiểm tra cửa sổ snapshot vẫn foreground, bounds không đổi, control visible và enabled. Chưa xác minh hậu điều kiện sau click.
- `click_element` và `set_text` đã được gate bởi form elicitation và audit cục bộ. Client phải khai báo capability; nếu không, action bị chặn. `set_text` hiển thị đúng giá trị cho host để người duyệt kiểm tra; host có thể ghi nhận nội dung này ngoài audit của AncharView. README hướng dẫn đặt VS Code ở chế độ manual approval.
- Giới hạn còn lại: server không thể xác thực người trả lời elicitation là người thật. VS Code có tool-approval controls, nhưng cần kiểm thử GUI theo permission mode đang dùng; Allow all/Autopilot có thể tự phản hồi.
- Whitelist role dùng để bỏ tên trường nhập là heuristic theo role phổ biến, không phải lớp DLP tổng quát; ứng dụng tùy biến có thể công bố role khác.

## 7. Lịch sử Git liên quan

- `1cee6e3`: snapshot repo ban đầu.
- `059198b`: prototype MCP server Windows C#.
- `06e560a`: migration sang Python MCP đa nền tảng, source, tests, README và cấu hình hiện tại.
- `94eb42e`: làm rõ cây source trong README và thêm báo cáo triển khai.

Báo cáo này mô tả phạm vi đã triển khai; các mục trong phần giới hạn là hướng phát triển tiếp theo, không được xem là tính năng đã hoàn thành.

## 8. Đánh giá mức sẵn sàng sử dụng thực tế

### Kết luận ngắn

AncharView hiện là **prototype kỹ thuật có thể thử nghiệm có giám sát**, chưa nên xem là agent điều khiển desktop production hoặc chạy không giám sát. Windows đã qua smoke test đọc UIA và MCP; chưa có end-to-end test thao tác ứng dụng. Linux mới được rà code, chưa chạy trên desktop Linux thật. Các guard P0 về phạm vi capture, foreground Linux, coordinate fallback và consent/audit đã được thêm; consent vẫn phụ thuộc hành vi MCP host và chưa xác minh người thật.

### Phát hiện ưu tiên cao

1. **Đã xử lý: phạm vi ảnh thiếu bounds.** `DesktopBackend.capture()` fail-closed nếu không có bounds hợp lệ; test bao phủ thiếu bounds và kích thước rỗng. Ảnh tự động không còn chuyển thành capture cả monitor/toàn output trong các trường hợp này.
2. **Đã xử lý: Linux không đoán foreground.** Backend chỉ trả về khi có đúng một cửa sổ `ACTIVE`; nếu không thì trả lỗi yêu cầu chọn `window_id`.
3. **Đã giảm rủi ro: fallback click Windows.** Cache giữ window ID và bounds tại thời điểm quan sát. Coordinate fallback chỉ thực hiện nếu cùng window còn foreground, bounds không đổi, control visible và enabled. Vẫn cần test UIA thật cho stale element và xác minh hậu điều kiện.
4. **Consent không chứng minh người thật phê duyệt.** Mọi click/set_text yêu cầu client khai báo form elicitation và bị chặn nếu không accept; prompt `set_text` hiển thị giá trị chính xác. Tuy vậy MCP host/Agent có thể tự tạo phản hồi hoặc lưu prompt. README chỉ cách yêu cầu VS Code manual approval; cần xác nhận session không ở Allow all/Autopilot. Chưa có allowlist ứng dụng hay cơ chế xác minh riêng cho Send/Delete/Pay.

### Phát hiện ưu tiên tiếp theo

- MCP elicitation/audit đã bao phủ click và set_text, gồm preview đúng giá trị nhập; chưa có allowlist ứng dụng hoặc xác minh danh tính người duyệt. Không chạy tự động Send/Delete/Pay.
- `max_nodes` giới hạn số node được xếp vào kết quả, nhưng trên Windows `wrapper.children()` tạo danh sách con trước khi cắt; giao diện có container rất rộng vẫn có thể chậm hoặc tốn bộ nhớ.
- Matching task và chọn vision dựa trên chuỗi từ khóa. Từ đồng nghĩa, ngôn ngữ khác, mục tiêu mơ hồ và substring trùng có thể làm chọn sai node hoặc bật/tắt ảnh không như mong muốn.
- Test hiện tập trung vào policy thuần. Chưa có test backend giả lập cho stale element, cửa sổ không active, thiếu bounds, lỗi chụp, disabled control, hay kết quả action; chưa có regression test UIA thật.
- `pyproject.toml` khai báo extra Linux `pyautogui`, nhưng adapter hiện tại không dùng nó. Cần bỏ dependency gây kỳ vọng sai hoặc triển khai rõ input fallback với quyền/giới hạn riêng.
- VS Code MCP config mặc định là đường dẫn virtualenv Windows; Linux phải chỉnh thủ công. Cần kiểm chứng quy trình cài sạch trên từng nền tảng và giảm cấu hình thủ công nếu muốn phân phối rộng.

## 9. Lộ trình thực dụng

### P0: bảo vệ desktop và dữ liệu

- [x] Không chụp toàn màn hình ngầm khi bounds cửa sổ thiếu; fail-closed.
- [x] Không đoán foreground Linux; yêu cầu chọn `window_id` nếu trạng thái `ACTIVE` không duy nhất.
- [x] Kiểm tra foreground, bounds, visibility và enabled trước coordinate fallback Windows.
- [x] Yêu cầu MCP elicitation trước mọi click/set_text; fail-closed nếu client không hỗ trợ hoặc không accept; ghi audit JSONL local không có text/ảnh.
- [x] Chặn mutation nếu MCP client không khai báo form elicitation; hiển thị chính xác giá trị `set_text` cho client và không ghi nó vào audit local.
- [x] Hướng dẫn cấu hình VS Code yêu cầu duyệt thủ công cho `click_element`/`set_text` bằng Chat: Manage Tool Approval hoặc `chat.tools.eligibleForAutoApproval`.
- [ ] Kiểm thử end-to-end trong VS Code Manual permissions: xác minh form elicitation xuất hiện, từ chối không đổi UI và chấp nhận chỉ chạy một lần.
- [ ] Server không thể chứng minh phản hồi accept đến từ người thật hoặc ngăn host giữ prompt/value; cần giữ host tin cậy và giám sát người dùng.

### P1: chứng minh dùng được trên hai nền tảng

- Đã có unit tests cho guard capture, foreground, fallback, consent và audit; tiếp tục tạo test backend cho cây rỗng, stale IDs, node cap, lỗi action và redaction.
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

Đánh giá này là code review theo source hiện tại, không phải chứng nhận an toàn hoặc kết quả kiểm thử Linux. P0 consent/audit có unit test/helper và MCP tool-schema smoke test; chưa kiểm thử end-to-end với VS Code approval UX, chưa xác minh hậu điều kiện UIA và chưa chạy Linux thật. Server không thể tự xác thực người duyệt; cần host bật xác nhận thủ công. Chưa giới thiệu là công cụ desktop production.

## 10. Giấy phép

Repo sử dụng Apache License 2.0. Toàn văn nằm trong `LICENSE`, README liên kết tới điều khoản, và metadata package khai báo SPDX `Apache-2.0`. Không tự điền chủ sở hữu bản quyền vào mẫu phụ lục; tên chủ sở hữu cụ thể cần được chủ dự án xác nhận nếu muốn thêm copyright notice riêng.

## 11. Mục tiêu kết nối Agent

Yêu cầu sản phẩm do chủ dự án bổ sung: AncharView cần kết nối dễ dàng với mọi Agent có khả năng tương tác PC.

### Ý nghĩa thực tế

- MCP là giao diện tích hợp chuẩn: mọi Agent có MCP client và hỗ trợ tool qua stdio có thể dùng cùng bộ tool mà không cần AncharView biết nhà cung cấp Agent.
- Không thể hứa tương thích trực tiếp với Agent không hỗ trợ MCP. Những Agent đó cần MCP bridge/adapter hoặc transport mà cả hai phía cùng hỗ trợ.
- Hiện cấu hình có sẵn tập trung vào VS Code; Linux còn phải sửa đường dẫn interpreter thủ công. Vì vậy khả năng tương thích giao thức đã có, nhưng trải nghiệm “kết nối dễ dàng với tất cả Agent” chưa hoàn tất.

### Điều kiện để đạt mục tiêu

- Giữ schema tool trung lập với nhà cung cấp, có mô tả/JSON schema rõ và kiểm thử bằng MCP Inspector hoặc client độc lập.
- Cung cấp hướng dẫn cấu hình ngắn cho các MCP host phổ biến; xác minh cài đặt sạch trên Windows và Linux.
- Cung cấp một lệnh khởi chạy ổn định qua virtualenv/package, tránh cấu hình phụ thuộc đường dẫn Windows/Linux.
- Chỉ bổ sung HTTP/Streamable HTTP khi có nhu cầu Agent cụ thể; nếu bật, giới hạn localhost, xác thực và quyền truy cập desktop rõ ràng.
- Duy trì test tương thích giao thức độc lập với OS; backend UIA/AT-SPI vẫn là phần riêng theo nền tảng.
(theo mình nghĩ nếu muốn phù hợp cho tất cả thì mình làm theo kiểu chung, cái nào có hỗ trợ MCP thì sử dụng, mình thì cũng ko làm gì cao siêu mà chỉ là hỗ trợ một chút như cách chúng ta đã thiết kế "đây chỉ là ý kiến thảo luận ko cần làm ngay")