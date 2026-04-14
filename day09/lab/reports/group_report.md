# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Group-D2-2
**Thành viên:**
| Tên | Vai trò | Email |
|-----|---------|-------|
| Nguyễn Trần Hải Ninh | Supervisor Owner, Worker Owner, MCP Owner | 26ai.ninhnth@vinuni.edu.vn |
| Phạm Đăng Phong | Trace & Docs Owner | 26ai.phongpd@vinuni.edu.vn |

**Ngày nộp:** 14/04/2026 
**Repo:** D2-2/day09
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Hướng dẫn nộp group report:**
> 
> - File này nộp tại: `reports/group_report.md`
> - Deadline: Được phép commit **sau 18:00** (xem SCORING.md)
> - Tập trung vào **quyết định kỹ thuật cấp nhóm** — không trùng lặp với individual reports
> - Phải có **bằng chứng từ code/trace** — không mô tả chung chung
> - Mỗi mục phải có ít nhất 1 ví dụ cụ thể từ code hoặc trace thực tế của nhóm

---

## 1. Kiến trúc nhóm đã xây dựng (150–200 từ)

> Mô tả ngắn gọn hệ thống nhóm: bao nhiêu workers, routing logic hoạt động thế nào,
> MCP tools nào được tích hợp. Dùng kết quả từ `docs/system_architecture.md`.

**Hệ thống tổng quan:**
Nhóm sử dụng kiến trúc LangGraph chuẩn với trọng tâm là 1 Supervisor phân phối lệnh và 3 specific Workers (`retrieval_worker`, `policy_worker` và `synthesis_worker`). Dữ liệu di chuyển trong pipeline được bọc thông qua một TypedDict State Object thống nhất. Tất cả mọi tools gọi data bên thứ ba đều phải tuân thủ chuẩn MCP protocol. Cấu trúc hệ thống chạy độc lập tạo thuận tiện cho việc đánh giá metrics của tập test questions từ bên ngoài.

**Routing logic cốt lõi:**
Supervisor điều tiết request (Routing) dựa trên sức mạnh của một LLM Classifier được cấu trúc ngặt nghèo bởi hệ Schema (Pydantic). Đầu tiên hệ thống trích xuất (parse) ý định (intent) của câu prompt, so sánh với hệ mô tả của các worker có sẵn, sau đó xuất ra label chính xác worker sẽ tiếp quản tiếp theo.

**MCP tools đã tích hợp:**
- `search_kb`: Công cụ kết nối đến vector database cho phép `retrieval_worker` làm truy xuất nội dung tài liệu.
- `get_ticket_info`: Công cụ truy vấn status hệ thống nội bộ để `policy_worker` kiểm tra và phân loại các task về IT hỗ trợ KH có mang SLA.
- `check_access_permission`: Dùng khi user cố gắng truy vấn các hệ thống hoặc chức năng cần bảo mật vượt cấp quyền.

---

## 2. Quyết định kỹ thuật quan trọng nhất (200–250 từ)

> Chọn **1 quyết định thiết kế** mà nhóm thảo luận và đánh đổi nhiều nhất.
> Phải có: (a) vấn đề gặp phải, (b) các phương án cân nhắc, (c) lý do chọn phương án đã chọn.

**Quyết định:** Sử dụng LLM-based Routing trong Supervisor Node thay cho Keyword-based Routing để điều tiết Traffic.

**Bối cảnh vấn đề:**
Hệ thống phải đối mặt với các câu truy vấn phức tạp của user mà trong đó các từ khóa hay bị trùng lặp ý nghĩa. Lấy ví dụ, khi KH phàn nàn "Chính sách của ticket kỹ thuật nhà mạng chậm quá", nếu dùng Keyword với chữ `chính sách`, hệ thống lọt mẹo phân tới `policy_worker`, nhưng intent thật sự là hối thúc kỹ thuật thì lại phải đi qua `ticket_worker` để xem progress.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| Keyword-Based | Latency siêu thấp (chỉ vài mili-giây), dễ code. Giảm chi phí token LLM. | Kém linh hoạt do phụ thuộc NLP cứng, tỉ lệ routing lỗi cực kỳ cao khi từ vựng bị hỗn tạp. |
| LLM-Based with JSON schema | Comprehension tuyệt đối dựa trên sự suy diễn ngữ nghĩa, hiểu ngầm rất tốt. | Latency cao (suy tăng +~300-500ms), tiêu thụ tokens LLM cho trạm gác đầu cuối. |

**Phương án đã chọn và lý do:**
Nhóm chấp nhận hi sinh một mức ping delay cho bước routing và đưa vào LLM-Based làm cốt lõi vì sự đánh đổi rất đáng giá. Việc rẽ nhánh nhầm trong Multi-Agent sinh ra hiệu ứng domino khi tools đằng sau liên tục trigger báo lỗi vì không thấy dữ liệu hợp lý, kéo theo Time-to-Answer còn tăng gấp bội (thường tốn lại vài nghìn mili-giây cho error retry). Làm chậm Supervisor một tí sẽ cứu giúp toàn bộ phần Pipeline đằng sau thông thoáng.

**Bằng chứng từ trace/code:**
```json
{
  "supervisor_route": "ticket_worker",
  "route_reason": "User intent implies a technical delay on an existing issue despite the mention of 'policy'. Ticket worker is best suited to retrieve progress.",
  "latency_ms": 451,
  "confidence": 0.88
}
```

---

## 3. Kết quả grading questions (150–200 từ)

> Sau khi chạy pipeline với grading_questions.json (public lúc 17:00):
> - Nhóm đạt bao nhiêu điểm raw?
> - Câu nào pipeline xử lý tốt nhất?
> - Câu nào pipeline fail hoặc gặp khó khăn?

**Tổng điểm raw ước tính:** 85 / 96

**Câu pipeline xử lý tốt nhất:**
- ID: `gq02` — Lý do tốt: Truy vấn yêu cầu bóc tách policy thuần túy. Worker Retrieval thực thi đúng `search_kb`, tổng hợp (synthesis) ra đúng quy trình điều khoản mà không bị hallucinate. Trace latency chỉ mất ~800ms cho việc đọc doc.

**Câu pipeline fail hoặc partial:**
- ID: `gq05` — Fail ở đâu: System không check chéo khi thiếu data thực từ tài liệu.
  Root cause: MCP server gọi tool trả về rỗng vì ID không tồn tại nhưng thay vì báo HITL thì mô hình tự chém gió thêm (hallucinate) làm sai lệch factual answer.

**Câu gq07 (abstain):** Nhóm xử lý thế nào?
Nhóm áp một rule hệ thống chặt lên LLM ở `synthesis_worker`: *"Dừng lại và return Abstain nếu không thể truy xuất bằng chứng tài liệu MCP hỗ trợ"*. Pipeline in ra `"hitl_triggered": true` tại Trace gq07 và request review người dùng khi tài liệu nội bộ chọi nhau với policy chuẩn.

**Câu gq09 (multi-hop khó nhất):** Trace ghi được 2 workers không? Kết quả thế nào?
Thành công cục bộ. Dữ liệu truy vết ghi nhận Tool Call gọi tuần tự 2 node là `policy_worker` để hỏi rules cho refund và sau đó lặp vòng qua `ticket_worker` để xác đáng danh hiệu KH đang có đủ điều kiện. Trả lời được context chung.

---

## 4. So sánh Day 08 vs Day 09 — Điều nhóm quan sát được (150–200 từ)

> Dựa vào `docs/single_vs_multi_comparison.md` — trích kết quả thực tế.

**Metric thay đổi rõ nhất (có số liệu):**
Latency trung bình (Avg. Time to response). Trong Lab day 08 Single-agent RAG, hệ thống trả lời toàn bộ đều quanh mức <900ms. Tuy nhiên tại Lab multi-agent day 09, các câu test có độ khó đa bước tăng vọt lên mức 1600ms - 2200ms chia đều do phải trao đổi dữ liệu (pass state) giữa 3 node liên tục qua API. Ngược lại, Confidence đo được trên file Trace tăng rõ rệt nhờ specialized worker bóp hẹp được context prompt.

**Điều nhóm bất ngờ nhất khi chuyển từ single sang multi-agent:**
Trạng thái quản lý đồ thị (State Graph Lifecycle) của bộ khung LangGraph là vô cùng rất nhạy cảm. Quá trình trace phát hiện ra chỉ một node báo completion sai key finish sẽ ép Pipeline vào vòng lặp vô hạn (Infinite loop) mà không sập ngay lập tức, tốn rất nhiều API cost. 

**Trường hợp multi-agent KHÔNG giúp ích hoặc làm chậm hệ thống:**
Đối chiếu với các câu dạng `Chit-chat` hoặc Greeting đơn thuần như `"Chào bạn, hôm nay thế nào?"`, hệ thống Single agent trả lời một hit ngay tức khắc. Multi-agent hệ thống lôi vô routing -> policy classifier -> v..v gây tốn thêm trung bình ~600ms vô giá trị. Tính năng over-engineering cho các queries quá tốn kém.

---

## 5. Phân công và đánh giá nhóm (100–150 từ)

> Đánh giá trung thực về quá trình làm việc nhóm.

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Ninh | Xây Graph, MCP server, Workers logic | 1, 2, 3 |
| Phong | Evaluation scripts, Trace logs, Report | 3, 4 |

**Điều nhóm làm tốt:**
Đạt tiến độ ổn định ở công đoạn thiết kế LangGraph. Ninh đã triển khai MCP Server rất nhanh để có thể tách biệt tool integration ra khỏi mảng business, hỗ trợ việc nâng cấp hay cắm code test từ Phong hiệu quả cực cao. Phong xuất form Evaluation logic độc lập.

**Điều nhóm làm chưa tốt hoặc gặp vấn đề về phối hợp:**
Quá trình debug đồ thị khá gian nan vì log cơ sở ban đầu không in cặn kẽ payload trao đổi ở các sub-graph. Hai bạn thỉnh thoảng mất đồng bộ do Output State Schema đổi chuẩn. 

**Nếu làm lại, nhóm sẽ thay đổi gì trong cách tổ chức?**
Nhóm sẽ xây dựng chuẩn file Integration API Test (Mock) trước. Code tới đâu, thả trace mock JSON test tới đó để test các workers biệt lập thay vì code cụm vào graph mới debug.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì? (50–100 từ)

> 1–2 cải tiến cụ thể với lý do có bằng chứng từ trace/scorecard.

Nhóm sẽ lập tức cấu hình luồng **Semantic Caching Layer** kẹp ngay trước Supervisor node. Do file trace eval trong tập test question và grading questions bộc lộ nhiều câu hỏi lặp lại keyword và context tới 80%, nếu gọi Cache hit cho các câu giống nhau hệ thống sẽ triệt tiêu được hoàn toàn ~400ms routing latency không cần thiết cho user experience.

---

*File này lưu tại: `reports/group_report.md`*  
*Commit sau 18:00 được phép theo SCORING.md*
