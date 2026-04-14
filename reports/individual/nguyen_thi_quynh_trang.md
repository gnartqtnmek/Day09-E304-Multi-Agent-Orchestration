# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Thị Quỳnh Trang  - 2A202600406
**Vai trò trong nhóm:** M3 — MCP Owner / Policy Tool Worker (Integration Specialist)  
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

Tôi phụ trách vai trò M3, tập trung vào tích hợp MCP và policy worker. Hai file chính tôi làm là `mcp_server.py` và `workers/policy_tool.py`. Ở `mcp_server.py`, tôi triển khai `TOOL_SCHEMAS`, `TOOL_REGISTRY`, `list_tools()` và `dispatch_tool()` để worker có thể gọi tool theo một interface chung. Các tool tôi làm là `tool_search_kb`, `tool_get_ticket_info`, `tool_check_access_permission` (kèm `tool_create_ticket` dạng mock).

Ở `workers/policy_tool.py`, tôi viết `_call_mcp_tool()`, `analyze_policy()` và `run()`. Luồng xử lý gồm: gọi `search_kb` khi thiếu context, phân tích policy exception, và gọi thêm `get_ticket_info` khi task có tín hiệu ticket/P1. Phần này nối trực tiếp với supervisor của M1: supervisor phải route đúng và set `needs_tool`, khi đó output của tôi (`policy_result`, `mcp_tools_used`) mới được synthesis dùng đúng.

Bằng chứng: commit liên quan là `8009096`; test worker độc lập cho kết quả `mcp_calls=2`, tools gọi là `search_kb` và `get_ticket_info`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Tôi chọn kiến trúc “schema discovery + dispatch tool” trong `mcp_server.py`, thay vì cho policy worker gọi thẳng từng hàm.

Tôi cân nhắc hai lựa chọn khác: viết `if/else` trực tiếp trong worker (nhanh nhưng coupling cao), hoặc dựng HTTP MCP server thật ngay sprint 3 (chuẩn hơn nhưng tốn thời gian). Tôi chọn phương án trung gian: chuẩn hóa interface MCP bằng schema + registry + dispatch, nhưng chạy mock in-process để kịp tiến độ.

Hiệu quả là policy worker chỉ cần `_call_mcp_tool(tool_name, input)` và giữ được contract nhất quán cho trace (`tool`, `input`, `output`, `error`, `timestamp`). Điều này giúp debug dễ hơn vì có thể kiểm tra rõ worker gọi tool nào, input gì, trả về gì.

Trade-off tôi chấp nhận: chưa có boundary mạng thật nên chưa test được lỗi transport/auth như production; toàn bộ vẫn cùng process.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** Tool-call trace của policy worker không ổn định khi state đầu vào thiếu key log.

**Symptom:** Trong trace `artifacts/traces/run_20260414_170434.json`, câu hỏi đã route vào `policy_tool_worker`, có `needs_tool=true`, nhưng `mcp_tools_used` rỗng. Như vậy phần trace chưa chứng minh được worker đã gọi MCP.

**Root cause:** Worker chưa phòng thủ đầy đủ với state truyền từ node khác. Khi thiếu các list như `workers_called`, `history`, `mcp_tools_used`, log bị thiếu hoặc không nhất quán.

**Cách sửa:** Tôi thêm `state.setdefault(...)` cho các key bắt buộc ở đầu `run()`, rồi tách rõ 3 bước: gọi `search_kb` khi thiếu chunks, phân tích policy exception, và gọi `get_ticket_info` nếu task có ticket/P1/Jira. Mỗi lần gọi đều append vào `mcp_tools_used` và `history`.

**Bằng chứng trước/sau:**
- Trước: `run_20260414_170434.json` có `needs_tool: true` nhưng `mcp_tools_used: []`.
- Sau (test worker độc lập): `mcp_calls= 2`, `tools=['search_kb', 'get_ticket_info']`, history ghi đủ hai lần gọi MCP.

Kết quả sau sửa cho thấy trong phạm vi worker, trace tool-call đã đúng format và dễ kiểm tra hơn.

---

## 4. Tôi tự đánh giá đóng góp của mình

Điểm tôi làm tốt nhất là chuẩn hóa phần MCP theo contract rõ ràng: schema, registry, dispatch và format log tool-call. Nhờ vậy worker có thể test độc lập và debug theo từng lớp.

Điểm tôi chưa tốt là integration end-to-end với graph chưa phản ánh đầy đủ số lần gọi MCP trong mọi trace. Module chạy tốt khi test riêng, nhưng cần phối hợp tốt hơn với orchestration.

Nhóm phụ thuộc vào tôi ở năng lực gọi tool và xử lý exception policy. Nếu phần tôi chưa xong thì Sprint 3 không đạt tiêu chí MCP. Ngược lại, tôi phụ thuộc vào M1 ở bước wiring route/node và phụ thuộc người chạy trace để xác nhận lại artifacts.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ làm đúng một cải tiến: hoàn tất wiring để pipeline luôn đi qua `workers/policy_tool.run` ở các câu policy/multi-hop, rồi chạy lại `eval_trace.py` cho gq09. Lý do là trace run `run_20260414_170434` vẫn có `needs_tool=true` nhưng `mcp_tools_used=[]`, tức lợi ích MCP chưa phản ánh đầy đủ ở mức end-to-end. Cải tiến này tác động trực tiếp tới điểm Sprint 3 và chất lượng debug theo route.
