# Datum — Text-to-SQL BI Copilot

Hệ thống trợ lý BI nội bộ: hỏi dữ liệu bằng tiếng Việt/Anh → SQL an toàn → kết quả có kiểm chứng.
Thiết kế: `docs/superpowers/specs/2026-09-26-text2sql-design.md`.

## Chạy nhanh

```bash
make up          # tạo .env (JWT_SECRET ngẫu nhiên) và khởi động toàn bộ stack
make logs        # theo dõi bootstrap: migrate → seed warehouse → demo users
```

Tài khoản demo (mật khẩu `demo1234`): `viewer@demo.vn`, `analyst@demo.vn`, `admin@demo.vn`.

## Phát triển

```bash
make test-api    # cần Docker (testcontainers)
make lint-api
```
