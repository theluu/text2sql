# Text2SQL — Trợ lý BI nội bộ (Design Spec)

- **Ngày:** 2026-09-26
- **Trạng thái:** Chờ duyệt
- **Stack:** FastAPI · PostgreSQL (+pgvector) · React · Docker

---

## 0. Mục tiêu & bối cảnh

### Người dùng yêu cầu
- Hệ thống Text-to-SQL có ứng dụng thực tế cao, thể hiện năng lực Senior AI Engineer.
- Stack: FastAPI, PostgreSQL, React, Docker. UI chuyên nghiệp.
- Bắt buộc có: **Eval Harness**, **Guardrails**, **AI-as-a-Judge**, **Model failover + rule-based fallback**, **HITL**.

### Đã chốt qua brainstorming
- **Use case:** BI nội bộ doanh nghiệp e-commerce/retail. Nhân viên kinh doanh/vận hành hỏi dữ liệu bằng ngôn ngữ tự nhiên.
- **LLM:** multi-provider. Chuỗi Claude → OpenAI → Gemini → Ollama (local, tùy chọn) → rule-based.
- **HITL:** theo mức rủi ro, có vòng phản hồi. Duyệt/sửa → few-shot + golden set.
- **Ngôn ngữ:** song ngữ Việt + Anh, cả câu hỏi và UI.
- **Kiến trúc:** pipeline tất định nhiều bước (không dùng agent tự do, không dùng framework Vanna/LangChain SQLAgent).

### Tiêu chí thành công
1. `docker compose up` là chạy toàn bộ hệ thống, có dữ liệu demo và 3 tài khoản demo (viewer/analyst/admin).
2. Execution Accuracy (EX) ≥ 80% trên golden set (khoảng 120 case) với chuỗi mặc định. Guardrail recall = 100% trên các case adversarial.
3. Demo được trực tiếp:
   - (a) hỏi → có kết quả kèm biểu đồ và trace;
   - (b) câu rủi ro → vào review → analyst duyệt → user nhận kết quả, và câu tương tự sau đó tự chạy nhờ few-shot;
   - (c) bật chaos tắt provider → thấy failover trong trace;
   - (d) tắt mọi LLM → rule-based fallback vẫn trả lời câu phổ biến.
4. CI chặn PR khi EX giảm quá 2 điểm hoặc có case adversarial bị lọt.

### Ngoài phạm vi v1
Kết nối DB tùy ý của người dùng, SSO/OAuth, fine-tune model, Grafana/Prometheus, thông báo email/Slack, mobile layout đầy đủ, multi-tenant.

---

## 1. Kiến trúc & services

| Service | Vai trò |
|---|---|
| `web` | React + Vite + TS, build tĩnh chạy qua nginx; proxy `/api` |
| `api` | FastAPI: auth, pipeline orchestrator, REST + SSE |
| `worker` | arq: chạy eval harness, re-embed nền |
| `app-db` | Postgres 16 + pgvector: metadata, audit, HITL, eval, embeddings |
| `warehouse` | Postgres 16: dữ liệu retail. API kết nối bằng role `readonly` (chỉ SELECT, `statement_timeout=10s`) |
| `redis` | Cache, rate limit theo user, trạng thái circuit breaker |
| `ollama` | Tùy chọn (`--profile local-llm`) |

**Nguyên tắc:**
- **Defense in depth:** kể cả khi mọi guardrail tầng ứng dụng thất bại, DB vẫn không cho ghi, có timeout, và PII được che qua view.
- **Streaming:** `POST /api/query` trả SSE. Mỗi bước pipeline phát sự kiện `step` (bắt đầu/kết thúc/lỗi), cuối cùng là sự kiện `result`.
- **Observability:** log JSON (structlog), trace OpenTelemetry cho từng step, bảng `llm_calls` ghi token/chi phí/độ trễ/provider/kết quả. Dashboard đọc trực tiếp từ DB.

### Warehouse (dữ liệu demo)
- 12 bảng: `regions, stores, employees, customers, categories, products, inventory, promotions, orders, order_items, payments, returns`.
- Seed khoảng 100k dòng bằng Faker locale `vi_VN`. Dữ liệu có tính mùa vụ và phân phối thực tế như Tết, 11/11 và các sản phẩm bán chạy theo power-law.
- Cột PII: `customers.email`, `customers.phone`, `customers.address`, `employees.salary`.
- View `v_customers_masked` và `v_employees_masked` dành cho viewer. Bảng gốc chỉ `analyst` và `admin` được phép đọc (allowlist tầng app + GRANT theo role DB riêng: `wh_viewer`, `wh_analyst`).

---

## 2. Pipeline & module backend

```
backend/app/
  core/        config (pydantic-settings), db, security (JWT), logging, telemetry
  pipeline/
    orchestrator.py        PipelineContext + chạy tuần tự các Step, phát sự kiện SSE
    steps/
      input_guard.py       phát hiện injection, lọc phạm vi, độ dài, nhận diện ngôn ngữ
      rewriter.py          viết lại câu hỏi nối tiếp thành câu độc lập (3 lượt gần nhất)
      schema_linker.py     pgvector top-k bảng/cột/metric + glossary
      fewshot.py           top-k verified_examples theo embedding
      generator.py         prompt → LLMRouter → {sql, rationale, self_confidence}
      sql_validator.py     kiểm tra AST bằng sqlglot, allowlist, tự thêm LIMIT
      cost_guard.py        EXPLAIN (FORMAT JSON) so với ngưỡng
      repair.py            đưa lỗi validator/EXPLAIN/thực thi lại cho LLM, tối đa 2 lần
      judge.py             AI-as-a-Judge
      risk_gate.py         AUTO_EXECUTE | NEEDS_REVIEW | REJECT
      executor.py          chạy trên warehouse theo role, có timeout
      output_guard.py      che PII, giới hạn dòng, tóm tắt NL, gợi ý chart_spec
  llm/
    base.py                Protocol LLMProvider.complete(messages, json_schema, timeout) -> LLMResponse
    anthropic.py openai.py gemini.py ollama.py fake.py
    router.py              failover chain, retry/backoff, circuit breaker, timeout budget
    rule_based.py          intent templates VI/EN
  semantic/
    warehouse.yaml         mô tả bảng/cột VI+EN, metric, join, cờ pii
    loader.py embedder.py
  hitl/                    review_service, feedback_service, promotion (→ few-shot/golden)
  eval/                    runner, metrics, comparators, cassette record/replay
  api/routes/              auth, query, conversations, review, eval, admin, dashboard
```

### Hợp đồng dữ liệu
- `PipelineContext`: `question, user, lang, rewritten_question, linked_schema, fewshots, candidates[], attempts, judge_verdict, risk_decision, result, trace[]`.
- Mỗi step là `async def run(ctx) -> StepResult{status, detail}`, được bọc bằng decorator ghi `pipeline_steps` và phát sự kiện SSE.
- Mọi provider trả `LLMResponse{content(json), model, provider, input_tokens, output_tokens, latency_ms, cost_usd}`.

### Semantic layer (`warehouse.yaml`)
- Nguồn sự thật cho mô tả nghiệp vụ, metric và PII. Ví dụ metric: `doanh_thu/revenue = SUM(order_items.quantity * order_items.unit_price * (1 - order_items.discount))`, loại trừ đơn `status='cancelled'`.
- Được embed vào `schema_embeddings` kèm `schema_version` (hash của file). Khi file đổi thì re-embed.

### Cache
- Key = hash(câu hỏi đã chuẩn hóa, schema_version, role, prompt_version). TTL 1 giờ.
- Chỉ cache kết quả `AUTO_EXECUTE` đã pass judge, hoặc kết quả đã được người duyệt.

---

## 3. Guardrails, failover, AI-as-a-Judge

### 3.1 Guardrails (5 lớp)

| Lớp | Cơ chế | Ví dụ code chặn |
|---|---|---|
| L1 Input | Heuristic + từ khóa VI/EN + bộ phân loại LLM rẻ (injection, ngoài phạm vi, yêu cầu ghi) | `INJECTION_SUSPECTED`, `OUT_OF_SCOPE`, `WRITE_INTENT` |
| L2 Prompt | Schema/ví dụ đặt trong thẻ phân cách; system prompt cấm làm theo chỉ dẫn nằm trong dữ liệu | — |
| L3 SQL tĩnh | Đúng 1 câu lệnh `SELECT`/`WITH`; allowlist bảng/cột theo role; cấm `pg_*`, `information_schema`, `COPY`, `dblink`, `pg_sleep`, `lo_*`, `SET`, `;`; `LIMIT ≤ 1000` | `NON_SELECT`, `MULTI_STATEMENT`, `FORBIDDEN_OBJECT`, `COLUMN_NOT_ALLOWED` |
| L4 Cost/DB | EXPLAIN cost > `max_cost` → chặn; nằm trong `[gray_cost, max_cost]` → review; role DB readonly + timeout | `COST_TOO_HIGH`, `DB_TIMEOUT` |
| L5 Output | Che PII theo role, giới hạn dòng, audit | `PII_MASKED` (thông tin) |

Mỗi sự kiện được ghi vào `guardrail_events` và trả thông báo thân thiện theo `lang`.

### 3.2 Failover & fallback
- **Chuỗi** cấu hình trong `app_settings.llm_chain` (mặc định: anthropic `claude-sonnet-5` → openai → gemini → ollama → rule_based). Chỉ provider có API key mới được đưa vào chain.
- **Mỗi provider:** timeout riêng; tổng budget 20 giây; tối đa 2 lần retry với exponential backoff + jitter, chỉ cho 429/5xx/timeout. Parse JSON lỗi → coi như lỗi, chuyển provider kế.
- **Circuit breaker (Redis):** 5 lỗi trong 60 giây → `open` trong 30 giây → `half_open` cho qua 1 request thử → thành công thì `closed`.
- **Chaos:** `app_settings.chaos.disabled_providers[]` khiến provider bị coi như trả lỗi. Dùng để demo.
- **Rule-based:** khoảng 25 intent (doanh thu theo thời gian/khu vực/danh mục/cửa hàng, top N sản phẩm/khách hàng, tồn kho thấp, tỷ lệ hoàn hàng, AOV, số đơn, tăng trưởng MoM/YoY…).
  - Trích tham số bằng regex + từ điển (mốc thời gian VI/EN như "quý 3 năm nay", "last month"; tên khu vực/danh mục khớp mờ với giá trị thật; N).
  - Kết quả luôn có `used_fallback=true` và badge "Chế độ dự phòng". Confidence trích tham số < 0.8 thì đưa vào review.
  - Không khớp intent nào → trả lời rõ ràng là không xử lý được, kèm câu hỏi gợi ý. Không bịa SQL.
- **Embedding failover:** provider API → `bge-m3` local. Nếu cả hai đều lỗi, linking dùng tìm kiếm từ khóa (Postgres full-text) trên semantic layer.

### 3.3 AI-as-a-Judge
- **Judge khác vendor với generator** (lấy provider khả dụng đầu tiên trong chain mà khác vendor). Nếu chỉ còn một vendor thì dùng chính nó và gắn nhãn `same_vendor_judge`.
- **Đầu vào:** câu hỏi, schema đã link, SQL, cột + tối đa 20 dòng preview.
- **Rubric** (mỗi tiêu chí 1–5, có lý do): `intent`, `schema_selection`, `joins_filters`, `aggregation`, `result_sanity`.
- **Đầu ra:** `{verdict: pass|fail|uncertain, score (0–1), issues[], suggested_fix?}`.
- **Self-consistency:** chỉ bật khi câu hỏi được phân loại `hard` (heuristic: nhiều thực thể, so sánh theo thời gian, window). Sinh thêm 2 ứng viên và so tập kết quả. Tỷ lệ đồng thuận được đưa vào confidence.
- **Confidence** = `0.2·self_confidence + 0.5·judge_score + 0.3·agreement` (khi không có self-consistency thì agreement=1 và trọng số chuẩn hóa lại). Trọng số nằm trong `app_settings` và được hiệu chỉnh dựa trên dữ liệu harness.

### 3.4 Risk gate
- `REJECT`: guardrail L1/L3/L4 chặn cứng.
- `NEEDS_REVIEW` nếu một trong các điều kiện: judge `fail|uncertain`; `confidence < 0.7`; viewer truy vấn chạm cột PII; dùng fallback với confidence trích tham số < 0.8; cost nằm trong vùng xám.
- `AUTO_EXECUTE`: các trường hợp còn lại.
- Ngưỡng nằm trong `app_settings.risk`, chỉnh được trên UI Admin.

---

## 4. HITL & Eval Harness

### 4.1 HITL
1. `NEEDS_REVIEW` → tạo `review_items(reasons[], priority)` với `priority = risk_weight × tuổi chờ`. Người hỏi thấy trạng thái "Đang chờ chuyên viên dữ liệu xác nhận", lý do, SQL nháp và preview. Preview chỉ hiện khi không có lý do PII hoặc cost.
2. Analyst: claim → xem ngữ cảnh, issue của judge, trace → sửa SQL (Monaco diff) → **Chạy thử** (qua L3–L5) → **Duyệt / Sửa và duyệt / Từ chối (lý do) / Trả lại hỏi thêm**.
3. Khi đã có quyết định: cập nhật `query_runs`, đẩy sự kiện tới người hỏi (SSE kênh thông báo, fallback polling 15 giây).
4. **Vòng phản hồi:**
   - duyệt/sửa → `verified_examples` (embed, dùng ngay làm few-shot);
   - tick `add_to_golden` → `eval_cases(source=review)`;
   - human verdict ≠ judge verdict → `judge_disagreements`;
   - 👎 của người dùng trên kết quả tự chạy → tạo review item hồi tố với reason `USER_DOWNVOTE`.
5. Toàn bộ quyết định được audit (người làm, thời điểm, diff).

### 4.2 Eval Harness
- **Dataset:** `backend/eval/datasets/*.yaml` được seed vào `eval_cases`. Khoảng 120 case song ngữ; độ khó easy/medium/hard/extra; tag `aggregation, join3, time_window, window_fn, ambiguous, adversarial, pii_access`; `expected_behavior ∈ {answer, reject, review}`; kèm `role` để chạy.
- **Metrics:**
  - EX: so tập kết quả, bỏ qua thứ tự trừ khi gold có ORDER BY; float so với dung sai 1e-6 tương đối; tên cột không quan trọng.
  - ESM: so AST sqlglot đã chuẩn hóa.
  - Behavior accuracy.
  - Guardrail precision/recall trên các case `adversarial`.
  - Judge: precision/recall khi bắt SQL sai (so với EX) và Cohen's κ so với nhãn người.
  - Recall@k của schema linking.
  - Latency p50/p95, $/query, tỷ lệ failover.
- **Chế độ chạy:** `chain` (mặc định), `provider=<x>` (ép một provider), `rule_based` (đo mức sàn).
- **Chạy qua:** `make eval SUITE=smoke|full MODE=...` (CLI) hoặc trang Evaluation (job arq, tiến độ qua SSE).
- **Tái lập:** `eval_runs` lưu `git_sha, prompt_version, model_chain, mode`. Hỗ trợ so sánh 2 run: case tốt lên/kém đi.
- **CI:** suite `smoke` (30 case) chạy với **cassette** (response LLM đã ghi lại, phát lại tất định). Gate: EX giảm ≤ 2 điểm so với baseline đã commit (`eval/baseline.json`) và 0 case adversarial bị lọt.

---

## 5. Data model (`app-db`)

```
users(id, email, name, role[viewer|analyst|admin], password_hash, created_at)
conversations(id, user_id, title, created_at)
query_runs(id, conversation_id, user_id, question, lang, rewritten_question, final_sql,
           status[answered|pending_review|rejected|failed], risk_decision, confidence,
           provider_used, used_fallback, guardrail_code, row_count, latency_ms, cost_usd,
           cache_hit, result_preview jsonb, chart_spec jsonb, summary, prompt_version, created_at)
pipeline_steps(id, query_run_id, step, status, started_at, duration_ms, detail jsonb)
llm_calls(id, query_run_id NULL, eval_result_id NULL, purpose[generate|judge|repair|rewrite|classify|embed],
          provider, model, attempt, outcome[ok|timeout|error|circuit_open|parse_fail|chaos],
          input_tokens, output_tokens, latency_ms, cost_usd, created_at)
judge_verdicts(id, query_run_id, judge_model, verdict, score, rubric jsonb, issues jsonb, same_vendor)
guardrail_events(id, query_run_id, layer, code, detail jsonb, created_at)
user_feedback(id, query_run_id, user_id, rating[up|down], comment, created_at)
review_items(id, query_run_id, reasons text[], priority, status[open|claimed|approved|edited|rejected|returned],
             assignee_id, original_sql, final_sql, reviewer_note, add_to_golden, created_at, resolved_at)
judge_disagreements(id, review_item_id, judge_verdict, human_verdict, created_at)
verified_examples(id, question, lang, sql, source[review|seed|feedback], embedding vector(1024),
                  approved_by, active, created_at)
schema_embeddings(id, object_type[table|column|metric|glossary], object_ref, text,
                  embedding vector(1024), schema_version)
eval_cases(id, suite, question, lang, role, gold_sql, expected_behavior, difficulty, tags text[],
           source[seed|review], active)
eval_runs(id, suite, git_sha, prompt_version, model_chain jsonb, mode, status, started_at,
          finished_at, summary jsonb)
eval_results(id, eval_run_id, eval_case_id, predicted_sql, behavior, ex_match, esm_match,
             judge_verdict, latency_ms, cost_usd, error, trace jsonb)
app_settings(key PK, value jsonb, updated_by, updated_at)
```

- Migration: Alembic. ORM: SQLAlchemy 2.0 async + asyncpg. Index HNSW cho các cột `embedding`.
- Kích thước embedding cố định 1024. Model có chiều khác thì cấu hình `dimensions` (API) hoặc dùng `bge-m3` (1024 gốc).

---

## 6. Frontend

**Stack:** React 18, TypeScript strict, Vite, TanStack Query + Router, Tailwind (design tokens qua CSS variables), Radix UI, Monaco, Recharts, i18next (VI mặc định, EN).

**Định hướng thẩm mỹ: "Analyst's instrument panel"**
- Font: IBM Plex Sans / Plex Sans Condensed (tiêu đề) / Plex Mono (SQL, số, trace). Đều hỗ trợ đầy đủ tiếng Việt.
- Màu: light nền `#F6F4EF`, dark nền `#14161A`; nhấn cobalt `#2F5BEA`.
- Trạng thái: tự chạy = xanh rêu, chờ review = hổ phách, bị chặn = đỏ gạch, dự phòng = xám tím.
- Đường kẻ mảnh, lưới dày thông tin, `font-variant-numeric: tabular-nums`. Trace pipeline là timeline ngang, các bước sáng dần theo SSE.

**Màn hình:**
1. **Login:** kèm nút đăng nhập nhanh 3 tài khoản demo.
2. **Ask:**
   - sidebar hội thoại;
   - luồng hỏi–đáp với result card (tóm tắt, chart tự chọn, bảng có xuất CSV, SQL có giải thích, badge confidence/provider/fallback, 👍/👎);
   - panel Trace (timeline, judge, guardrail, token/chi phí);
   - trạng thái rỗng hiển thị câu hỏi gợi ý VI/EN.
3. **Review Queue (analyst+):** bảng ưu tiên + bộ lọc; màn chi tiết chia đôi (ngữ cảnh/issue | Monaco diff + chạy thử); phím tắt A/E/R.
4. **Evaluation (analyst+):** danh sách run, nút Run; chi tiết gồm hàng KPI (EX, guardrail recall, judge κ, p95, $/query), phân tích theo độ khó/tag, bảng case; chế độ so sánh 2 run.
5. **Ops dashboard (admin):** tỷ lệ auto/review/reject theo thời gian, sức khỏe provider (trạng thái circuit), tỷ lệ failover, top guardrail codes, chi phí theo ngày.
6. **Admin settings:** sắp thứ tự LLM chain (kéo thả), ngưỡng risk gate, công tắc chaos, trình xem semantic layer.

**Chất lượng:** hỗ trợ bàn phím đầy đủ, contrast AA, skeleton loading, error boundary; tối ưu cho ≥1280px, dưới mức đó chuyển sang bố cục một cột.

---

## 7. API (tóm tắt)

| Method | Path | Role | Mô tả |
|---|---|---|---|
| POST | `/api/auth/login` | — | JWT |
| POST | `/api/query` | viewer+ | SSE: `step`, `result`, `error` |
| GET | `/api/conversations[/{id}]` | viewer+ | Lịch sử |
| POST | `/api/query-runs/{id}/feedback` | viewer+ | 👍/👎 |
| GET | `/api/notifications/stream` | viewer+ | SSE thông báo kết quả review |
| GET/POST | `/api/review[/{id}/claim|approve|edit|reject|return|dry-run]` | analyst+ | HITL |
| GET/POST | `/api/eval/runs[/{id}]`, `/api/eval/compare` | analyst+ | Harness |
| GET | `/api/dashboard/ops` | admin | Chỉ số vận hành |
| GET/PUT | `/api/admin/settings` | admin | Chain, ngưỡng, chaos |
| GET | `/api/health` | — | Liveness + trạng thái provider |

---

## 8. Chiến lược test
- **Unit (pytest):**
  - `sql_validator` (≥60 case tấn công: DML trong CTE, `;`, comment, `pg_sleep`, catalog, cột không được phép);
  - `rule_based` (intent + tham số VI/EN);
  - `router` (FakeProvider: timeout, 429, parse_fail, circuit open/half-open, chaos, hết budget);
  - `risk_gate` (bảng quyết định);
  - các comparator EX.
- **Integration:** testcontainers (pgvector/pg16) chạy pipeline đầy đủ với `FakeLLMProvider` theo kịch bản; kiểm tra role readonly không thể ghi/DDL.
- **Contract:** mỗi adapter với cassette → đúng `LLMResponse`.
- **Eval:** smoke (CI, cassette) và full (thủ công/hằng đêm).
- **Frontend:** Vitest + Testing Library; Playwright E2E cho 3 luồng: hỏi → có kết quả; hỏi → review → duyệt → nhận kết quả; chaos → thấy failover.
- **Tooling:** ruff, mypy `--strict`, eslint, `tsc --noEmit`; `make test`, `make lint`, `make eval-smoke`; GitHub Actions. TDD cho từng module.

---

## 9. Thứ tự triển khai (mỗi mốc demo được)
1. **Nền tảng:** monorepo, docker-compose, app-db + warehouse (schema, seed, role), Alembic, auth JWT, khung React + design tokens + login.
2. **Pipeline lõi:** semantic layer + embedding + linking, generator (Anthropic), validator, executor, SSE, màn Ask cơ bản.
3. **Guardrails** 5 lớp + bộ test tấn công + che PII theo role.
4. **LLM router:** các adapter, failover, circuit breaker, chaos, rule-based fallback.
5. **Judge + risk gate + repair + self-consistency**; Trace panel.
6. **HITL:** review queue, thông báo, vòng phản hồi few-shot/golden, feedback 👍/👎.
7. **Eval harness:** dataset, metrics, worker, trang Evaluation, cassette, CI gate.
8. **Ops dashboard, Admin settings,** hoàn thiện UI, README + sơ đồ kiến trúc + kịch bản demo.

## 10. Rủi ro & giảm thiểu
- **Chi phí LLM khi chạy eval:** dùng cassette cho CI; suite full chạy thủ công; theo dõi `$/query`.
- **Judge thiên lệch:** dùng judge khác vendor, đo κ trên nhãn người, lưu disagreement.
- **Tiếng Việt không dấu hoặc viết tắt:** chuẩn hóa (bỏ dấu song song) cho rule-based và glossary; có case eval riêng.
- **Rò rỉ PII qua aggregate** (vd. `GROUP BY email`): L3 allowlist cột theo role, áp dụng cho mọi vị trí trong AST, không chỉ SELECT list.
