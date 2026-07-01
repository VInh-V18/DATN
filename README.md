# AI Agent tự vận hành và đảm bảo an ninh hệ thống mạng trên nền tảng GNS3

Cài đặt tham chiếu theo đề cương đồ án tốt nghiệp: một AI Agent tích hợp bốn năng lực —
**Giám sát/AIOps**, **Tự khắc phục** (vòng lặp Observe–Think–Act), **Copilot hội thoại**
và **An ninh/SOC** — vận hành trên hạ tầng mạng mô phỏng GNS3, với LLM (Ollama/Qwen hoặc
Claude API) làm bộ não suy luận thông qua cơ chế tool-calling.

## Cấu trúc thư mục

```
backend/            FastAPI + agent runtime (Python)
  app/
    core/            config, database session
    models/          SQLAlchemy models (Bảng 3.4)
    schemas/         Pydantic schemas cho API
    gns3/            GNS3 REST API client (mục 2.4)
    automation/      Netmiko device client (mục 2.5)
    tools/           Đặc tả tool + tool executor (Bảng 3.3, mục 3.4)
    llm/             LLM client thống nhất (Ollama / Claude API)
    agent/           Vòng lặp Self-Healing Observe-Think-Act (mục 3.3.2)
    monitoring/      Collector, Isolation Forest, event correlation (mục 3.3.1)
    security/        Detection rules, MITRE ATT&CK mapping, playbook (mục 3.3.4)
    copilot/         Trợ lý hội thoại (mục 3.3.3)
    api/             FastAPI routers theo Bảng 3.2 + WebSocket
  tests/             pytest cho tool layer, anomaly detection, security rules
frontend/           React + TypeScript + Vite dashboard (mục 3.6)
docker-compose.yml  PostgreSQL, InfluxDB, Ollama, backend, frontend
```

## Chạy thử (development)

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # chỉnh sửa GNS3_URL, LLM_PROVIDER, ... cho phù hợp
uvicorn app.main:app --reload
python -m pytest       # chạy bộ test hiện có
```

Mặc định backend dùng PostgreSQL; có thể đổi `DATABASE_URL` sang SQLite khi phát triển
nhanh (ví dụ `sqlite:///./dev.db`) mà không cần sửa code.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Toàn bộ hệ thống qua Docker Compose

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

Sau khi khởi động: backend tại `http://localhost:8000`, frontend tại `http://localhost:5173`,
Ollama tại `http://localhost:11434`, InfluxDB UI tại `http://localhost:8086`.

Lưu ý: cần một GNS3 server đang chạy (`gns3server`) và một dự án đã có sẵn thiết bị; điền
`GNS3_URL`, `GNS3_PROJECT_ID` trong `backend/.env`, sau đó đăng ký các thiết bị (bảng
`devices`/`interfaces`/`topology_links`) tương ứng với node trong GNS3 để agent có thể quan
sát và điều khiển.

## Trạng thái hiện thực so với đề cương

Đã hiện thực khung kiến trúc đầy đủ cho cả bốn lớp chức năng (mục 3.2–3.4):

- GNS3 REST client + Netmiko wrapper (mắt xích giao thức, mục 2.3–2.5).
- Bộ 15 tool theo Bảng 3.3 cùng guardrails (danh sách lệnh cho phép, phân loại rủi ro,
  yêu cầu phê duyệt cho hành động rủi ro cao).
- LLM client hợp nhất cho Ollama (Qwen local) và Claude API.
- Vòng lặp Self-Healing đúng mã giả mục 3.3.2 (observe → think → guardrail → act → verify → rollback).
- Collector + Isolation Forest + tương quan sự kiện (mục 3.3.1).
- Rule-based detection (port scan / SYN flood / SSH brute-force) + ánh xạ MITRE ATT&CK +
  playbook phản ứng có phê duyệt (mục 3.3.4).
- Copilot hội thoại tách bạch hành động đọc (tự do) và hành động ghi (cần xác nhận) (mục 3.3.3).
- API đầy đủ theo Bảng 3.2 + WebSocket `/ws/events`.
- Dashboard React: Tổng quan, Topology, Sự cố (kèm phê duyệt), An ninh (kèm phê duyệt), Chat Copilot.

Các hạng mục còn để ngỏ cho các giai đoạn tiếp theo của kế hoạch (Bảng 5.4, GĐ1–GĐ6):

- Dựng lab GNS3 thật với 5–10 thiết bị (R1–R3, SW1–SW2, H1–H2, IoT, máy tấn công) và đăng
  ký vào bảng `devices`/`interfaces`/`topology_links`.
- Kịch bản fault injection KB01–KB10 (Bảng 5.2) và script đo đạc các chỉ số ở Bảng 5.3
  (tỉ lệ tự khắc phục, MTTR, precision/recall/F1).
- Kết nối syslog/netflow thật vào `SecurityDetectionEngine.ingest_*` (hiện expose sẵn API
  nhưng chưa có nguồn dữ liệu thật).
- Huấn luyện/đánh giá Isolation Forest trên dữ liệu thực nghiệm thay vì cửa sổ trượt mặc định.
- Xác thực người dùng (JWT) cho bảng `users`/phân quyền — hiện API chưa yêu cầu đăng nhập.
