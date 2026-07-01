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
    api/             FastAPI routers theo Bảng 3.2 + WebSocket + auth (JWT)
  alembic/           Migration schema (thay thế create_all khi lên production)
  scripts/
    gns3_lab.py        Dựng lab GNS3 + seed devices/interfaces/topology_links (Bảng 5.1)
    fault_injection.py Kịch bản gây lỗi chủ động KB01-KB10 (Bảng 5.2)
    evaluate.py        Tính chỉ số đánh giá định lượng (Bảng 5.3)
  lab_topology.yaml  Khai báo topology lab (chỉnh template_name theo GNS3 server thật)
  tests/             pytest cho tool layer, anomaly detection, security rules, auth
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

Quản lý schema bằng Alembic (khuyến nghị cho môi trường ổn định, thay cho `create_all` lúc dev):

```bash
alembic upgrade head                                   # áp dụng migration mới nhất
alembic revision --autogenerate -m "mô tả thay đổi"     # tạo migration mới sau khi sửa models
```

### Dựng lab GNS3 và seed dữ liệu

```bash
# Chỉnh sửa backend/lab_topology.yaml cho khớp template GNS3 server của bạn, sau đó:
python -m scripts.gns3_lab create --seed-db     # tạo project+node+link trên GNS3 và ghi vào DB
python -m scripts.gns3_lab seed-db              # chỉ đồng bộ lại DB nếu lab đã tồn tại
```

### Fault injection & đánh giá (Bảng 5.2, 5.3)

```bash
python -m scripts.fault_injection list                                   # xem 10 kịch bản KB01-KB10
python -m scripts.fault_injection KB01 --device R2 --interface GigabitEthernet0/1
python -m scripts.evaluate                                                # báo cáo Bảng 5.3
python -m scripts.evaluate --labels eval_labels.json --json               # kèm nhãn thực tế, xuất JSON
```

### Xác thực

```bash
curl -X POST localhost:8000/api/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"engineer1","password":"secret123","role":"engineer"}'
curl -X POST localhost:8000/api/auth/login -d 'username=engineer1&password=secret123'
```
Token trả về (`access_token`) dùng làm Bearer token cho các endpoint phê duyệt
(`POST /api/incidents/{id}/approve`, `POST /api/security/alerts/{id}/approve` — UC4).

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
- API đầy đủ theo Bảng 3.2 + WebSocket `/ws/events` + xác thực JWT (đăng ký/đăng nhập,
  bảo vệ hai endpoint phê duyệt UC4 bằng vai trò engineer/admin).
- Alembic migration cho toàn bộ schema (Bảng 3.4).
- `scripts/gns3_lab.py` dựng project + node + link trên GNS3 theo `lab_topology.yaml`
  (Bảng 5.1) và đồng bộ vào DB.
- `scripts/fault_injection.py` hiện thực 10 kịch bản KB01–KB10 (Bảng 5.2).
- `scripts/evaluate.py` tính các chỉ số ở Bảng 5.3 (tỉ lệ tự khắc phục, MTTR, thời gian
  phản hồi Copilot, tỉ lệ phản ứng an ninh đúng...) trực tiếp từ DB; các chỉ số cần nhãn
  thực tế (độ chính xác chẩn đoán, recall phát hiện tấn công) nhận nhãn qua `--labels`.
- Dashboard React: Tổng quan, Topology, Sự cố (kèm phê duyệt), An ninh (kèm phê duyệt), Chat Copilot.

Các hạng mục còn để ngỏ cho các giai đoạn tiếp theo của kế hoạch (Bảng 5.4, GĐ1–GĐ6):

- Chạy `scripts/gns3_lab.py` trên một GNS3 server thật (cần đăng ký sẵn template thiết bị
  khớp với `lab_topology.yaml`) để có lab vật lý/ảo thật sự, thay vì chỉ kiểm thử bằng đơn vị.
- Chạy các kịch bản KB01–KB10 trên lab thật, thu thập nhãn thực tế (root cause, tấn công đã
  biết) rồi chạy `scripts/evaluate.py --labels ...` để có số liệu Bảng 5.3 đầy đủ.
- Kết nối syslog/netflow thật vào `SecurityDetectionEngine.ingest_*` (hiện expose sẵn API
  nhưng chưa có nguồn dữ liệu thật).
- Huấn luyện/đánh giá Isolation Forest trên dữ liệu thực nghiệm thay vì cửa sổ trượt mặc định.
- Áp JWT cho các endpoint đọc dữ liệu (hiện chỉ hai endpoint phê duyệt yêu cầu đăng nhập,
  phù hợp quy mô phòng lab).
