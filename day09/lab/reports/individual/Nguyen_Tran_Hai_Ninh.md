# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Trần Hải Ninh
**Vai trò trong nhóm:** Supervisor Owner, Worker Owner, MCP Owner  
**Ngày nộp:** 14/04/2026
**Độ dài yêu cầu:** 500–800 từ

---

> **Lưu ý quan trọng:**
> - Viết ở ngôi **"tôi"**, gắn với chi tiết thật của phần bạn làm
> - Phải có **bằng chứng cụ thể**: tên file, đoạn code, kết quả trace, hoặc commit
> - Nội dung phân tích phải khác hoàn toàn với các thành viên trong nhóm
> - Deadline: Được commit **sau 18:00** (xem SCORING.md)
> - Lưu file với tên: `reports/individual/[ten_ban].md` (VD: `nguyen_van_a.md`)

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

> Mô tả cụ thể module, worker, contract, hoặc phần trace bạn trực tiếp làm.
> Không chỉ nói "tôi làm Sprint X" — nói rõ file nào, function nào, quyết định nào.

**Module/file tôi chịu trách nhiệm:**
- File chính: `graph.py`, `mcp_server.py`, và các worker trong thư mục `workers/` (như `retrieval.py`, `synthesis.py`, `policy_tool.py`).
- Functions tôi implement: Logic của `run_graph`, code điều phối của `supervisor_node`, các node cho từng worker cụ thể và việc kết nối các tools vào MCP server.

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Tôi đảm nhiệm việc xây dựng kiến trúc cốt lõi của Multi-Agent bằng LangGraph. Toàn bộ request sẽ đi qua hệ thống điều phối (Supervisor) của tôi để xử lý logic, gọi các worker tương ứng, và sau cùng trả về kết quả dạng dictionary. Kết quả này chính là đầu vào (input) quan trọng để Phong có thể chạy file `eval_trace.py` xuất ra metrics, đo thời gian phản hồi (latency), và thống kê trace phục vụ cho phần Docs & Tracing.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**
Code trong file `graph.py` thiết lập State Graph cho các node, định nghĩa cụ thể luồng chuyển dữ liệu từ Supervisor tới Worker Node và ngược lại.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

> Chọn **1 quyết định** bạn trực tiếp đề xuất hoặc implement trong phần mình phụ trách.
> Giải thích:
> - Quyết định là gì?
> - Các lựa chọn thay thế là gì?
> - Tại sao bạn chọn cách này?
> - Bằng chứng từ code/trace cho thấy quyết định này có effect gì?

**Quyết định:** Sử dụng LLM-based routing kết hợp với cấu trúc dạng Structured Output (sử dụng Pydantic) thay vì sử dụng Keyword-based routing truyền thống cho thành phần `supervisor_node`.

**Lý do:**
Lựa chọn thay thế là áp dụng tìm kiếm từ khoá (Keyword-based) để điều phối task. Tuy keyword sẽ cho tốc độ rất nhanh, nhưng nó dễ đưa mồi nhử sai lệch đối với các truy vấn phức tạp hoặc yêu cầu đa bước (multi-hop). Việc sử dụng một LLM mạnh mẽ làm người kiểm soát (Supervisor) giúp hệ thống hiểu và phân tích sâu được đúng intent semantic của user, từ đó điều xe trúng tới `policy_worker` hay `retrieval_worker`.

**Trade-off đã chấp nhận:**
Sử dụng LLM đồng nghĩa với việc chấp nhận đánh đổi một lượng thời gian trễ (latency), thông thường độ trễ tăng khoảng ~300ms đến 500ms cho bước định tuyến đầu tiên so với Keyword routing. Tuy nhiên, tính chính xác và tỷ lệ fail của worker operation giảm xuống đáng kể, đảm bảo hệ thống không bị gọi nhầm Tool.

**Bằng chứng từ trace/code:**
```json
{
  "supervisor_route": "retrieval_worker",
  "route_reason": "User is asking for specific document references about coverage detail, requires factual data from retrieval worker.",
  "confidence": 0.95,
  "mcp_tools_used": ["search_kb"]
}
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

> Mô tả 1 bug thực tế bạn gặp và sửa được trong lab hôm nay.
> Phải có: mô tả lỗi, symptom, root cause, cách sửa, và bằng chứng trước/sau.

**Lỗi:** State của Graph mắc vào vòng lặp vô hạn (Infinite Loop) ở quá trình giao tiếp Worker và Supervisor.

**Symptom (pipeline làm gì sai?):**
Khi một worker xử lý xong tác vụ (VD `retrieval.py` tìm xong tài liệu) và chưa hoàn thiện câu trả lời, nó tự động nhảy ngược lại cho `supervisor_node`. Supervisor sau đó đánh giá thông tin và lại đẩy ngược về cho exactly worker đó. Vòng lặp này gây timeout và crash API sau nhiều lần lặp.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**
Lỗi nằm ở phần worker logic và cấu trúc điều hướng node trong `graph.py`. Các worker không update chính xác tham số chuyển tiếp trong state (VD `__end__` hoặc chuyển sang một node tổng hợp `synthesis`). Do LangGraph mặc định tuân theo điều hướng nếu không có hard limit trỏ đi rõ ràng.

**Cách sửa:**
Tôi đã điều chỉnh trong `graph.py` để sau vòng gọi công cụ (Tool Calling), output của tất cả các specific worker sẽ được hard-coded đưa thẳng vào node `synthesis` (nếu cần xử lý ngôn ngữ sinh ra) hoặc kết thúc (`__end__`), thay vì route lỏng lẻo về ngược supervisor.

**Bằng chứng trước/sau:**
> Trước khi sửa: `supervisor -> retrieval -> supervisor -> retrieval -> ... (Max steps reached)`
> Sau khi sửa: `supervisor -> retrieval -> synthesis -> __end__` với final answer trả về hoàn thiện.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

> Trả lời trung thực — không phải để khen ngợi bản thân.

**Tôi làm tốt nhất ở điểm nào?**
Tôi đã thiết kế quy trình LangGraph một cách gọn gàng, tách biệt rạch ròi các thành phần Supervisor và các Worker. Setup thành công MCP server để gọi được nhiều công cụ độc lập, giúp dự án dễ scale thêm các agent mới trong tương lai.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Việc log chi tiết hành vi bên trong tool calls chưa được thực sự tốt. Quá trình trace nhiều lúc mất giấu những API input nhỏ của tool do không ghi đệm lại.

**Nhóm phụ thuộc vào tôi ở đâu?** *(Phần nào của hệ thống bị block nếu tôi chưa xong?)*
Phong bắt buộc phải đợi file `graph.py` và luồng agent của tôi hoạt động mượt mà và trả ra được dict chứa các key đúng quy chuẩn (như latency, confidence, supervisor_route) để có thể phục vụ script đánh giá tự động (eval trace). 

**Phần tôi phụ thuộc vào thành viên khác:** *(Tôi cần gì từ ai để tiếp tục được?)*
Tôi cần sự phản hồi liên tục của Phong về các logs trace từ test questions. Thông qua những file xuất lỗi được Phong thông báo tôi mới biết hệ thống đang vướng route ở câu hỏi test số mấy để tinh chỉnh system prompt.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

> Nêu **đúng 1 cải tiến** với lý do có bằng chứng từ trace hoặc scorecard.
> Không phải "làm tốt hơn chung chung" — phải là:
> *"Tôi sẽ thử X vì trace của câu gq___ cho thấy Y."*

Tôi sẽ tích hợp **Streaming Tokens** ở phần node `synthesis`. Lý do là bởi các trace logs thuộc test set cho thấy phần tổng hợp (synthesis text gen) làm tăng avg_latency lên đến ~800-1200ms do đợi LLM sinh full văn bản. Tính năng streaming sẽ trực tiếp giảm Time-to-First-Token đáng kể cho user interface.

---

*Lưu file này với tên: `reports/individual/NguyenTranHaiNinh.md`*
