# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Phạm Đăng Phong 
**Vai trò trong nhóm:** Trace & Docs Owner  
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
- File chính: `eval_trace.py`, thư mục lưu dữ liệu log `artifacts/` và toàn bộ các file văn bản thuộc về tài liệu bao gồm `README.md` cùng file kết quả cuối `reports/group_report.md`.
- Functions tôi implement: `run_test_questions`, `run_grading_questions` (sẽ sinh ra dạng *.jsonl để dễ dàng nộp tự động chấm chuẩn), `analyze_traces`, và function đặc biệt `compare_single_vs_multi` nhằm phục vụ phần báo cáo thực nghiệm.

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Code đồ thị Multi-Agent và MCP do Ninh xây dựng sẽ đóng vai trò Blackbox API. Tôi lấy State Outputs do Ninh sinh ra và tự động đổ hàng loạt (batching) qua test set lên tới 15 câu hỏi. Công việc của tôi biến các output string chay ấy thành bảng so sánh số đo (hiệu năng, độ trễ và luồng phân phối điều hướng - routing distribution) phục vụ Docs Owner.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**
Sở hữu mã nguồn file `eval_trace.py`: Chức năng phân giải các logs `save_trace()` để dump log thông minh cho `grading_run.jsonl`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

> Chọn **1 quyết định** bạn trực tiếp đề xuất hoặc implement trong phần mình phụ trách.
> Giải thích:
> - Quyết định là gì?
> - Các lựa chọn thay thế là gì?
> - Tại sao bạn chọn cách này?
> - Bằng chứng từ code/trace cho thấy quyết định này có effect gì?

**Quyết định:** Phân tách và xuất Trace log của từng test question ra thành một file `.json` biệt lập, nằm gói gọn bên trong thư mục `artifacts/traces/` thay vì việc append (chèn nối tiếp) tất cả một cụm dữ liệu vi mô vào mảng lớn của một file trung tâm duy nhất (như eval.json).

**Lý do:**
Việc này đem lại khả năng đối rủi ro (Fault Tolerance) xuất sắc cho module Test. Nếu tôi gộp hết vào array của một tệp gốc, trong trường hợp API chạy lỗi giữa chừng (như đứt mạng giữa vòng lặp), array định dạng JSON sẽ bị hở hàm và khiến toàn bộ file hỏng structure, không thể deserialize được về sau. Khi lưu riêng từng ID question vào một file, tôi giảm thiểu tối đa việc corrupt format. Nếu rớt ở câu 12, ta vẫn sẽ dùng script load được 11 trace cũ nguyên bản một cách gọn lẹ.

**Trade-off đã chấp nhận:**
Chấp nhận việc I/O lưu tạo một lượng mẩu file lắt nhắt, gây vụn thư mục artifacts. Nhưng lượng question ít và dung lượng nhỏ hoàn toàn không ảnh hưởng tiến trình.

**Bằng chứng từ trace/code:**
Trong system:
`artifacts/traces/trace_q01.json`
`artifacts/traces/trace_q02.json`
...v.v độc lập.

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

> Mô tả 1 bug thực tế bạn gặp và sửa được trong lab hôm nay.
> Phải có: mô tả lỗi, symptom, root cause, cách sửa, và bằng chứng trước/sau.

**Lỗi:** Module `eval_trace.py` bị terminate (sập đổ đột ngột) và không chạy full cycle khi đụng câu hỏi lỗi.

**Symptom (pipeline làm gì sai?):**
Đang chạy batch testing 15 câu, có một câu bị execution exception ở MCP worker. Bất thình lình, process ngừng toàn cục for loop, văng báo màu đỏ báo API Timeout, và mất luôn chuỗi test result từ phía log sau câu đó. Không xuất được log grading final cho nhóm.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**
Tại khối `run_test_questions()` và `run_grading_questions()` tôi quên bọc vòng trigger model bằng cấu trúc xử lý Exception. Bất cứ worker lỗi sẽ văng exception throw xuyên graph lên tới cấp bash script.

**Cách sửa:**
Tôi thêm cụm `try... except Exception as e` bao quanh hàm invoke ở node đầu vào `run_graph`. Với lỗi bắt được, chương trình bỏ qua xử lí, log biến rỗng kèm message lỗi ở property "error" cho trace output, và để pipeline tiếp tục move on sang câu kế tiếp. 

**Bằng chứng trước/sau:**
> Trước: `[06/15] gq06: ... Traceback... Execution API Time out!` (Dừng hệ thống).
> Sau khi sửa Terminal log: `[06/15] gq06: ...  ✗ ERROR: API Connection Timeout... Done. 14 / 15 succeeded.`

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

> Trả lời trung thực — không phải để khen ngợi bản thân.

**Tôi làm tốt nhất ở điểm nào?**
Tổ chức thư mục trace sạch sẽ. Viết code thu nhận tự động hóa cho các metrics như latency trung bình, confidence matrix, tỉ lệ gọi MCP và có tuỳ biến CLI terminal bằng `--compare` chuẩn chỉ. Báo cáo đánh giá xuất file JSON khá tiện để bóc dòng.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Trace log chưa ghi vết chuyên sâu được `multi_hop_accuracy`, việc tính độ chính xác do tôi dựa vào manual testing (70%) thay vì có code bắt và phân tích sự sai lệch bằng semantic, dẫn tới tính thiếu khách quan.

**Nhóm phụ thuộc vào tôi ở đâu?** *(Phần nào của hệ thống bị block nếu tôi chưa xong?)*
Ninh và các bạn cần kết quả hàm `compare_single_vs_multi` của tôi để có số liệu viết bản Báo Cáo Nhóm (Group Report) cho Sprint 4, chứng tỏ sự tiến bộ so với pipeline cũ Lab 08. Ngoài ra phải có `grading_run.jsonl` từ máy tôi chạy lúc quá 17:00 chiều để nộp điểm.

**Phần tôi phụ thuộc vào thành viên khác:** *(Tôi cần gì từ ai để tiếp tục được?)*
Tôi bắt buộc Ninh phải truyền các khoá Output chuẩn xác mang tên `latency_ms` hay `mcp_tools_used` sang graph state cuối, thì mới có Data cho file Eval của tôi đo lường. Nếu dict graph output thiếu các trường này, chương trình gãy lập tức.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

> Nêu **đúng 1 cải tiến** với lý do có bằng chứng từ trace hoặc scorecard.
> Không phải "làm tốt hơn chung chung" — phải là:
> *"Tôi sẽ thử X vì trace của câu gq___ cho thấy Y."*

Tôi sẽ tích hợp tính năng **LLM-as-a-judge** thẳng vào hàm `analyze_traces`. Lý do là hiện tại trace không đo lường được tính chính xác ngữ nghĩa (Semantic accuracy), mà file JSON evaluation chỉ đo performance hardware/routing. Sự xuất hiện của LLM chấm điểm sẽ đối chiếu auto `result` với `expected_answer` trong dataset tạo ra một evaluation scorecard có base khoa học.

---

*Lưu file này với tên: `reports/individual/PhamDangPhong.md`*
