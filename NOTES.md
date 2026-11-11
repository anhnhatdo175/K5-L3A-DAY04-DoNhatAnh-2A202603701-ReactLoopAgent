# Ghi chú phân tích · Day 04

Họ và tên: Đỗ Nhật Anh
MSSV: 2A202603701

## 1. Case được chọn

- ID case: A5
- Câu trả lời của agent: Agent nói không tìm thấy incident năm 2025, nhưng sau đó liệt kê các incident gần đây từ năm 2026.
- Điểm ở lần chạy 1: 55/100

## 2. Bằng chứng trong trace

Dán đoạn trace chứng minh lỗi và nêu nguyên nhân có thể xảy ra.

```text
{"event":"tool","step":1,"name":"get_status","arguments":{"provider":"github","component":"GitHub Actions"},"result":{"matching_incidents_in_last_50":11,"incidents":[{"id":"t89g2q1800fr","updated_at":"2026-11-05T17:42:35.455Z"},{"id":"xr3myzj7ms51","updated_at":"2026-11-07T01:04:38.647Z"},{"id":"ntrfd2jqldn6","updated_at":"2026-10-28T22:29:49.032Z"},{"id":"q29p76qtnkyk","updated_at":"2026-11-05T00:04:42.627Z"},{"id":"8tzbpcnl75jp","updated_at":"2026-10-22T13:12:51.444Z"}],"note":"Chỉ tìm theo chuỗi trong 50 incident gần nhất; không tìm thấy không chứng minh không có sự cố."}
Câu trả lời sau đó nói không tìm thấy incident năm 2025 và liệt kê 5 incident trong kết quả gần đây năm 2026.
```

## 3. Thay đổi đã thực hiện

- Sửa gì, ở đâu: Bổ sung quy tắc vào SYSTEM_PROMPT trong agent.py: với truy vấn lịch sử hoặc yêu cầu danh sách đầy đủ, chỉ kết luận trong phạm vi thời gian tool bao phủ; không suy diễn từ 50 incident gần nhất và không liệt kê incident ngoài giai đoạn được hỏi như câu trả lời.
- Vì sao chọn thay đổi này: Trace cho thấy tool đã nêu giới hạn phạm vi, nhưng agent vẫn đưa ra kết luận vượt quá bằng chứng. Nhắc rõ giới hạn trong system prompt nhằm ngăn suy luận đó và tránh thông tin không liên quan.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 77.73/100 | 77.95/100 (+0.22) |
| Điểm case đã chọn | A5: 55/100 | A5: 75/100 (+20) |
| Số model calls | 73 (51 agent + 22 judge) | 69 (47 agent + 22 judge) |
| Token | 84,724 token; khoảng $0.01848 | 73,835 token; khoảng $0.01634 |

- Lỗi đã giải quyết: A5 không còn liệt kê năm incident 2026 như câu trả lời cho truy vấn năm 2025 và nêu rõ giới hạn dữ liệu 50 incident gần nhất. Điểm judge tăng từ 55 lên 75. H8 cũng tăng từ 65 lên 75 khi nêu giới hạn phạm vi dữ liệu.
- Lỗi còn lại hoặc mới xuất hiện: A5 chưa hoàn toàn chính xác; judge vẫn cho rằng câu “không xác nhận bất kỳ sự cố nào trong năm 2025” dễ bị hiểu thành kết luận không có incident, và phần nhắc incident năm 2026 còn thừa. Tổng điểm chỉ tăng 0.22. Một số case giảm điểm ở lần chạy sau: H2 100→50, H7 80→60, E2 90→75 và E3 80→65; các nhận xét của judge tập trung vào phân biệt incident lịch sử/hiện tại, bằng chứng và phạm vi ảnh hưởng. Vì mỗi phiên bản chỉ chạy một lần và judge cũng là LLM, không thể khẳng định các thay đổi này do riêng system prompt gây ra.

## 5. Giới hạn

- Cả hai lần đều dùng cùng cấu hình: OpenRouter `openai/gpt-4o-mini` cho agent và judge, `max_steps=8`, dataset core; cả hai chấm đủ 22/22 case. Judge dùng cùng model với agent nên có thể thiên lệch, và điểm không thay thế việc đọc expected, answer cùng trace.
- Snapshot cố định không phản ánh trạng thái hiện tại; status search chỉ bao phủ tối đa 50 incident gần nhất, nên không thể xác minh danh sách đầy đủ cho giai đoạn lịch sử như năm 2025.
- Mỗi phiên bản chỉ chạy một lần. LLM có thể trả lời khác nhau giữa các lượt, nên điểm tăng 0.22 và biến động từng case chưa đủ chứng minh quan hệ nhân quả với thay đổi prompt.
- Token và chi phí là tổng theo usage được ghi trong hai file (agent và judge); đây là số liệu do provider báo cáo, có thể thay đổi theo giá và cách tính của provider.
