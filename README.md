# Datum — Text-to-SQL BI Copilot

Trợ lý BI nội bộ cho doanh nghiệp bán lẻ. Người dùng hỏi dữ liệu bằng tiếng Việt hoặc tiếng Anh. Hệ thống sinh SQL, kiểm tra an toàn qua 5 lớp, nhờ một AI khác vendor chấm điểm, và câu nào rủi ro thì chuyên viên dữ liệu duyệt trước khi trả lời.

**Demo:** https://text2sql.themeshub.net · **Tổng quan dự án (PDF):** [Datum_Text2SQL_Overview.pdf](frontend/public/Datum_Text2SQL_Overview.pdf) ([bản trên site](https://text2sql.themeshub.net/Datum_Text2SQL_Overview.pdf))

Thiết kế: [`docs/superpowers/specs/2026-09-26-text2sql-design.md`](docs/superpowers/specs/2026-09-26-text2sql-design.md) · Kế hoạch triển khai: [`docs/superpowers/plans/`](docs/superpowers/plans/)

## Chạy nhanh

```bash
make up                  # tạo .env (JWT_SECRET ngẫu nhiên) và khởi động toàn bộ stack
open http://localhost:8080
```

Tài khoản demo (mật khẩu `demo1234`):

| Email | Vai trò | Thấy gì |
|---|---|---|
| `viewer@demo.vn` | Người xem | Hỏi dữ liệu. Email/SĐT khách được che, không thấy lương |
| `analyst@demo.vn` | Chuyên viên dữ liệu | + Duyệt câu trả lời, Đánh giá |
| `admin@demo.vn` | Quản trị | + Vận hành, Cấu hình |

### Bật mô hình AI

Chỉ provider có key mới được đưa vào chuỗi failover. Không có key nào thì hệ thống vẫn trả lời các câu phổ biến bằng **rule-based** (badge "Chế độ dự phòng"). Thêm vào `.env` (file tạo trước đây có thể chưa có các dòng này):

```bash
ANTHROPIC_API_KEY=sk-ant-...     # claude-sonnet-5 (sinh SQL)
OPENAI_API_KEY=sk-...            # judge khác vendor + embeddings (text-embedding-3-small, 1024d)
GEMINI_API_KEY=...
OLLAMA_BASE_URL=                 # tuỳ chọn: http://ollama:11434 với --profile local-llm
```

OpenAI đứng đầu chuỗi mặc định (đổi trên trang **Cấu hình**). Model mặc định `gpt-5-mini` (`OPENAI_MODEL`) chạy với `reasoning_effort=low` khi sinh SQL và `minimal` cho judge/phân loại (`OPENAI_REASONING_EFFORT`). Vì model reasoning chậm, mỗi lần gọi được chờ tối đa 30 giây và cả chuỗi 45 giây (`LLM_CALL_TIMEOUT_S`, `LLM_BUDGET_S`), thay cho budget 20 giây trong spec.

Sau đó chạy `docker compose up -d api worker`. `GET /api/health` cho biết provider nào đã được cấu hình và trạng thái circuit của từng provider.

## Kiến trúc

```mermaid
flowchart LR
  subgraph web["web (React + nginx)"]
    ASK[Hỏi dữ liệu] --- REV[Duyệt] --- EVAL[Đánh giá] --- OPS[Vận hành / Cấu hình]
  end
  web -- "/api (REST + SSE)" --> API
  subgraph API["api (FastAPI)"]
    direction TB
    L1[L1 input guard] --> RW[rewrite] --> LINK[schema linking<br/>pgvector + từ khoá] --> FS[few-shot đã duyệt]
    FS --> GEN[generate<br/>LLMRouter]
    GEN --> L3[L3 sqlglot guard] --> L4[L4 EXPLAIN cost] --> EXE[execute<br/>role read-only]
    EXE -. lỗi .-> REP[repair ≤2] -.-> L3
    EXE --> JUDGE[AI judge<br/>khác vendor] --> SC[self-consistency] --> GATE{risk gate}
    GATE -- AUTO --> L5[L5 che PII + tóm tắt + chart]
    GATE -- REVIEW --> HITL[review queue]
    GATE -- REJECT --> BLOCK[chặn]
  end
  GEN --> CHAIN["Claude → OpenAI → Gemini → Ollama → rule-based<br/>retry · circuit breaker · chaos · budget 20s"]
  API --> APPDB[(app-db<br/>Postgres + pgvector)]
  API --> WH[(warehouse<br/>wh_viewer / wh_analyst)]
  API --> REDIS[(redis<br/>circuit · cache · pub/sub)]
  WORKER[worker (arq)<br/>eval harness] --> APPDB
  WORKER --> WH
```

| Service | Vai trò |
|---|---|
| `web` | React 19 + Vite, phục vụ qua nginx, proxy `/api` (tắt buffering cho SSE) |
| `api` | FastAPI: pipeline, auth JWT, review, eval, ops/admin |
| `worker` | arq: chạy eval harness ngoài process API |
| `app-db` | Postgres 16 + pgvector: audit, HITL, eval, embeddings |
| `warehouse` | Dữ liệu bán lẻ khoảng 100k dòng (vi_VN). API chỉ kết nối bằng role read-only, timeout 10 giây, view che PII |
| `redis` | Circuit breaker dùng chung, cache kết quả, rate limit, thông báo |
| `ollama` | Tuỳ chọn, `docker compose --profile local-llm up -d` |

**Phòng thủ nhiều lớp:** kể cả khi mọi guardrail tầng ứng dụng đều thất bại, role DB vẫn không cho ghi, không gọi được `set_config`/`pg_sleep`, có `statement_timeout`, và viewer chỉ đọc được view đã che PII.

## Kịch bản demo

1. **Hỏi, xem biểu đồ và trace.** Đăng nhập `viewer`, bấm "Doanh thu theo khu vực trong quý này so với quý trước?". Dải pipeline sáng dần theo từng bước. Panel "Các bước xử lý" bên phải hiện bảng được chọn, provider, kết quả kiểm tra SQL, chi phí EXPLAIN, verdict của judge và cổng rủi ro.
2. **Rủi ro → duyệt → người hỏi nhận kết quả → câu tương tự tự chạy.**
   - Viewer hỏi `theo khu vực năm 2025` (thiếu metric nên độ tin cậy thấp). Câu trả lời chuyển sang **Chờ duyệt**.
   - Analyst mở **Duyệt câu trả lời**, xem diff SQL, bấm *Chạy thử* (chạy với quyền của viewer), rồi nhấn **A** để duyệt. Có thể tick "Thêm vào golden set".
   - Viewer nhận thông báo, câu trả lời chuyển sang "Đã trả lời".
   - Viewer hỏi lại gần giống ("Theo khu vực năm 2025?"). Lần này câu trả lời tự chạy với badge "SQL đã được duyệt" (tái dùng few-shot).
   - Câu chạm dữ liệu cá nhân của viewer ("Email khách hàng platinum") thì **luôn** phải duyệt.
3. **Failover (cần ít nhất 2 provider có key).** Admin vào **Cấu hình**, tick *Giả lập sự cố* cho `anthropic`, rồi Lưu. Hỏi lại một câu: trace bước "Sinh SQL" hiện `anthropic#1 chaos` rồi `openai#1 ok`. Trang **Vận hành** cho thấy tỷ lệ chuyển mô hình và trạng thái circuit.
4. **Tắt mọi LLM.** Tick chaos cho tất cả provider, hoặc không cấu hình key nào. Câu phổ biến vẫn được trả lời bằng rule-based ("Chế độ dự phòng"). Câu ngoài mẫu thì hệ thống nói rõ không xử lý được và gợi ý câu khác, không bịa SQL.
5. **Tấn công.** Thử "Bỏ qua mọi hướng dẫn trước đó…", "Xóa các đơn hàng bị hủy", "doanh thu'; DROP TABLE orders; --". Các câu này bị chặn ở L1/L3 kèm lý do.

## Eval harness

```bash
make eval SUITE=smoke MODE=chain          # 30 case; MODE=rule_based | provider=anthropic
make eval SUITE=full                       # 130 case song ngữ
make eval-record                           # ghi phản hồi LLM vào backend/eval/cassettes/ (cần key)
make eval-smoke                            # replay cassette + gate so với backend/eval/baseline.json
```

- **Metric:** EX (so tập kết quả, bỏ qua tên và thứ tự cột, dung sai 1e-6), ESM, độ chính xác hành vi (trả lời / duyệt / chặn), guardrail precision/recall, judge precision/recall/κ, recall@k của bước chọn bảng, latency p50/p95, $/câu, tỷ lệ failover/fallback. Có chia theo độ khó và nhãn.
- **CI** (`.github/workflows/ci.yml`) chạy smoke bằng cassette replay. PR bị chặn khi EX giảm quá 2 điểm hoặc có câu tấn công lọt.
- **Kết quả smoke (30 case):**

  | Chế độ | EX | Hành vi đúng | Chặn tấn công | p50 / p95 | $/câu |
  |---|---|---|---|---|---|
  | OpenAI `gpt-5-mini` + rule-based | **90,5%** | 90% | 100% | 10 s / 29 s | $0,0025 |
  | Chỉ rule-based (mức sàn, không LLM) | 81% | 83% | 100% | < 0,5 s | $0 |

- **Baseline CI** là mức sàn rule-based đo ở scale seed 0.05, vì CI không có key. Cassette phải được record trong đúng môi trường CI (cùng dữ liệu, cùng embedder) thì mới replay khớp được.
- Trang **Đánh giá** chạy suite qua worker, hiển thị tiến độ trực tiếp, KPI, phân tích theo độ khó/nhãn và từng case (gold SQL so với SQL sinh ra), và so sánh hai lần chạy.

## Phát triển

```bash
make test        # pytest (testcontainers: Postgres + Redis) + vitest
make lint        # ruff, mypy --strict, eslint, tsc
cd frontend && API_TARGET=http://localhost:8000 npm run dev   # hot reload, proxy /api
cd frontend && npx playwright test                             # E2E trên stack đang chạy (xem e2e/)
```

```
backend/app/
  pipeline/    orchestrator, sql_guard (L3), input_guard (L1), output (L5), judge, risk, generator, prompts
  llm/         anthropic (SDK chính thức), openai, gemini, ollama, router, circuit, rule_based, timeparse
  semantic/    warehouse.yaml (nguồn sự thật nghiệp vụ + PII), embedder, linker
  hitl/        review_service, feedback_service, notifications
  eval/        comparators, metrics, runner, cassette, seed
backend/eval/  datasets/golden.yaml, baseline.json, cassettes/
frontend/src/features/  ask, review, eval, ops, admin
```

## Ghi chú thiết kế

- Mốc thời gian tương đối ("tháng này", "quý trước") được tính theo `DATA_AS_OF` (ngày cuối của dữ liệu seed), nên kết quả và eval tái lập được.
- Không có key embedding thì linking và few-shot dùng embedder hashing cục bộ 1024 chiều (từ khoá không dấu). Có `OPENAI_API_KEY` thì chuyển sang embedding API và tự re-index khi khởi động.
- Anthropic được gọi qua SDK chính thức, dùng structured outputs (`output_config.format`). Router tự lo retry và backoff (`max_retries=0` ở SDK) để giữ trong budget 20 giây.
- Bảng màu biểu đồ (`--series-*`, `--chart-*`) đã qua kiểm tra độ phân biệt màu cho người mù màu và độ tương phản ở cả chế độ sáng và tối. Mỗi biểu đồ đều có legend và chế độ "Xem dạng bảng".
