# Piaxi: PaddleOCR VAT Invoice Recognition

> **Disclaimer: This project is a teaching case** designed to demonstrate PaddleOCR and FastAPI integration. **It is NOT suitable for production use.** Recognition results may contain inaccuracies — do not use them for real financial or legal purposes.

---

## Project Overview

**Piaxi** (票析) is a PaddleOCR PP-OCRv4-based VAT invoice OCR teaching case that uses a **region positioning + keyword mapping** dual strategy to extract structured invoice fields, and provides an **honest degradation mechanism** to inform users about result reliability.

Core recognition process:

1. **PaddleOCR PP-OCRv4** performs text detection and recognition, returning bounding box coordinates, text, and confidence scores
2. **Region positioning** — OCR text boxes are classified into layout regions based on their y-coordinate percentage (basic info, buyer info, amount info, seller info)
3. **Keyword mapping** — Within each region, characteristic keywords are searched; text near keywords is extracted as field values
4. **Honest degradation** — Three checks evaluate reliability:
   - Key field missing ratio > **30%** → flagged as `字段不完整` (incomplete fields)
   - Average confidence < **0.80** → flagged as `识别置信度偏低` (low confidence)
   - Field coverage < **60%** → flagged as `模板匹配不足` (insufficient template match)
   - Any trigger → `reliability.level = "low"`; otherwise `"high"`

---

## Features

- VAT invoice image OCR recognition (JPG / PNG / BMP)
- 16 key fields extracted, displayed in 4 groups: Basic Info, Amount Info, Buyer Info, Seller Info
- Honest degradation — low-reliability results are explicitly flagged with reasons, never misleading
- Desensitized display — company names, tax IDs, invoice numbers, and amounts are masked by default; individual fields can be revealed
- Original image annotation — OCR detection boxes drawn on the source image for visual verification
- JSON / CSV export — exported files retain full data; frontend displays desensitized versions
- Health check — real-time model loading status and inference device info
- Concurrency control — only one request processed at a time to prevent resource contention
- Fully local — no data uploaded to any third-party server; cleared from memory after recognition
- Privacy scanning — CI automatically detects sensitive information leaks in the code repository

---

## Technical Architecture

```
┌─────────────── Frontend (index.html + app.js) ─────────────┐
│  Drag-drop upload → /api/ocr → Structured table /          │
│  Original annotation / Desensitized display                 │
│  Health polling → /api/health → Status bar indicator        │
└────────────────────────┬────────────────────────────────────┘
                         │ multipart/form-data
                         ▼
┌─────────────── FastAPI (app/main.py) ──────────────────────┐
│  Concurrency lock · File validation · Format check          │
│  Exception handling · Services container: OCR + Template    │
└────────────────────────┬────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
┌───── OCRRunner ──────┐  ┌── InvoiceTemplate ──┐
│  PaddleOCR PP-OCRv4  │  │  Region positioning  │
│  Lazy load · Singleton│  │  (y%)                │
│  Device auto-detect   │  │  Keyword mapping     │
│  GPU/CPU              │  │  Desensitization     │
└───────────────────────┘  │  Reliability eval    │
                           └─────────────────────┘
```

### Module Responsibilities

| Module | File | Responsibility |
|--------|------|----------------|
| Configuration | `app/config.py` | Environment variable loading, threshold constraints, process-level singleton |
| OCR Engine | `app/ocr.py` | PaddleOCR lazy loading, device detection, inference calls |
| Invoice Template | `app/template.py` | Field definitions, region划分, KV mapping, reliability evaluation |
| Desensitization | `app/desensitize.py` | Company name / tax ID / invoice number / amount masking rules |
| Data Models | `app/schemas.py` | Pydantic request/response models, `extra="forbid"` strict contracts |
| Error Definitions | `app/errors.py` | Unified business exceptions, code + Chinese message + HTTP status |
| App Entry | `app/main.py` | Route registration, dependency injection, static file mounting |
| Privacy Scanner | `scripts/privacy_scan.py` | CI privacy leak detection (private keys, tokens, real company names, binary files) |

### Design Principles

- **Honest degradation** — low-confidence results are not hidden; reasons are clearly communicated
- **Minimal exposure** — API contracts use `extra="forbid"`; exceptions only expose code and public_message
- **Local-first** — all data processed locally; no third-party server uploads
- **Default desensitization** — frontend displays masked values by default; individual reveal; exports retain full data
- **Dependency injection** — factory pattern `create_app()`; tests inject mock services, production uses real services

---

## API Endpoints

### GET /

Returns the main page (`index.html`).

### GET /api/health

Health check — returns service status, model loading status, and inference device.

**Response example:**

```json
{
  "status": "ok",
  "model_status": "loaded",
  "device": "cpu"
}
```

| model_status | Meaning |
|---|---|
| `not_loaded` | Model not loaded yet (on first startup) |
| `loading` | Model is currently loading |
| `loaded` | Model loaded; ready for recognition |
| `error` | Model loading failed |

### POST /api/ocr

Invoice recognition — upload an image file, receive structured field results.

**Request:** `multipart/form-data`, field name `file`, supports JPG / PNG / BMP, max 10 MB.

**Response example:**

```json
{
  "groups": [
    {
      "name": "基础信息",
      "fields": [
        {
          "key": "invoice_number",
          "label": "发票号码",
          "value": "12345678",
          "confidence": 0.95,
          "desensitized": "12****78"
        }
      ]
    }
  ],
  "overall_confidence": 0.92,
  "reliability": {
    "level": "high",
    "reasons": []
  },
  "device": "cpu",
  "ocr_boxes": [
    {
      "box": [[100, 200], [200, 200], [200, 220], [100, 220]],
      "text": "发票号码",
      "confidence": 0.98
    }
  ]
}
```

**Low reliability response example:**

```json
{
  "reliability": {
    "level": "low",
    "reasons": ["字段不完整", "识别置信度偏低"]
  }
}
```

### Error Codes

| HTTP Status | code | message | Trigger |
|---|---|---|---|
| 413 | `FILE_TOO_LARGE` | 上传文件超过大小限制 | File exceeds 10 MB |
| 415 | `UNSUPPORTED_FORMAT` | 不支持该图片格式 | Non JPG/PNG/BMP format |
| 422 | `NO_TEXT_DETECTED` | 图片中未检测到文字 | OCR detected no text |
| 422 | `OCR_FAILED` | 图片识别失败，请确认图片清晰度 | PaddleOCR inference exception |
| 429 | `CONCURRENT_REQUEST` | 正在处理中，请稍后再试 | Duplicate concurrent request |
| 500 | `INTERNAL_ERROR` | 服务内部错误 | Unexpected internal exception |

---

## Requirements

- Python >= 3.11, < 3.14
- PaddlePaddle >= 3.0 (CPU version default; GPU version requires CUDA environment)
- Operating system: Windows / Linux / macOS

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Gooeto/paddleocr-invoice-extractor.git
cd paddleocr-invoice-extractor

# Create a virtual environment (recommended)
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies (optional, for testing and linting)
pip install -r requirements-dev.txt
```

On first recognition, PaddleOCR automatically downloads PP-OCRv4 model weights (~10 MB); subsequent runs use the local cache.

---

## Startup

```bash
# Development mode (auto-reload)
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Production mode
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

After startup, open `http://127.0.0.1:8000` in your browser.

Override defaults via environment variables or a `.env` file (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Listen address |
| `PORT` | `8000` | Listen port |
| `MAX_FILE_BYTES` | `10485760` | Max upload file size (bytes) |
| `OCR_USE_GPU` | `false` | Enable GPU inference |

---

## Testing

```bash
# Run unit tests
python -m pytest -q

# Run tests with coverage report
python -m pytest --cov=app --cov-report=term-missing

# Code format check
python -m ruff format --check app tests scripts
python -m ruff check app tests scripts

# Auto-fix format issues
python -m ruff format app tests scripts
python -m ruff check --fix app tests scripts

# Privacy scan (detect sensitive information leaks in the repo)
python scripts/privacy_scan.py

# Type checking
python -m mypy app
```

CI automatically runs: ruff format/check → privacy_scan → pytest (see `.github/workflows/tests.yml`).

---

## Privacy

- **Fully local** — all OCR inference runs locally; no images uploaded to third-party servers
- **No database** — no invoice data stored; cleared from memory after recognition
- **Default desensitization** — sensitive fields are masked in frontend display (company names, tax IDs, invoice numbers, amounts)
- **Per-field reveal** — users can click to view individual full values, avoiding wholesale exposure
- **Dual-track export** — frontend displays desensitized versions; exported files retain full data; user chooses
- **Privacy scanner** — CI automatically detects private keys, tokens, real company names, and binary files in the repository

---

## Template & Fields

The VAT invoice template defines 16 key fields, classified into 4 groups:

| Group | Field | Label (Chinese) | Keywords |
|---|---|---|---|
| Basic Info | `invoice_code` | 发票代码 | 发票代码, 代码 |
| Basic Info | `invoice_number` | 发票号码 | 发票号码, 号码, No |
| Basic Info | `invoice_date` | 开票日期 | 开票日期, 日期 |
| Basic Info | `check_code` | 校验码 | 校验码 |
| Amount Info | `amount_without_tax` | 不含税金额 | 合计, 金额, 不含税 |
| Amount Info | `tax_rate` | 税率 | 税率 |
| Amount Info | `tax_amount` | 税额 | 税额 |
| Amount Info | `amount_with_tax` | 价税合计 | 价税合计, 合计 |
| Buyer Info | `buyer_name` | 购方名称 | 购方名称, 购买方, 名称 |
| Buyer Info | `buyer_tax_number` | 购方纳税人识别号 | 购方纳税人识别号, 购方识别号, 纳税人识别号 |
| Buyer Info | `buyer_address_phone` | 购方地址、电话 | 购方地址, 地址电话, 地址、电话 |
| Buyer Info | `buyer_bank_account` | 购方开户行及账号 | 购方开户行, 开户行及账号, 开户行 |
| Seller Info | `seller_name` | 销方名称 | 销方名称, 销售方, 名称 |
| Seller Info | `seller_tax_number` | 销方纳税人识别号 | 销方纳税人识别号, 销方识别号 |
| Seller Info | `seller_address_phone` | 销方地址、电话 | 销方地址 |
| Seller Info | `seller_bank_account` | 销方开户行及账号 | 销方开户行 |

Region划分 (by invoice layout y-coordinate percentage):

| Region | y Range | Corresponding Field Group |
|---|---|---|
| header | 0% – 15% | — |
| basic_info | 15% – 28% | Basic Info |
| buyer_info | 28% – 45% | Buyer Info |
| item_detail | 45% – 62% | — (not extracted) |
| amount_info | 62% – 75% | Amount Info |
| seller_info | 75% – 90% | Seller Info |
| footer | 90% – 100% | — (not extracted) |

---

## FAQ

### First startup is slow?

On the first recognition, PaddleOCR downloads PP-OCRv4 model weights (~10 MB). Download speed depends on network conditions. Subsequent runs reuse the local cache.

### How to enable GPU inference?

Set `OCR_USE_GPU=true` and ensure the CUDA version of PaddlePaddle is installed. The system automatically detects the device:

```bash
# Install GPU version PaddlePaddle (requires CUDA)
pip install paddlepaddle-gpu

# Start with GPU enabled
OCR_USE_GPU=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Recognition accuracy is low?

This project is a teaching case using simple region positioning + keyword mapping, with known limitations:

- Non-standard invoice layouts may have inaccurate region划分
- Keyword matching may misidentify similar keywords
- Blurred, tilted, or obstructed images significantly reduce accuracy

Check `reliability.level` and `reliability.reasons` to assess result credibility.

### Why only one request at a time?

The service uses a thread lock to limit concurrency to 1, because PaddleOCR inference consumes significant memory. Concurrent requests may cause resource contention. For multi-concurrency, deploy multiple instances with a reverse proxy load balancer.

### How to adjust reliability thresholds?

Override default thresholds via environment variables (see `app/config.py`):

| Variable | Default | Description |
|---|---|---|
| `FIELD_MISSING_RATIO_THRESHOLD` | 0.30 | Field missing ratio threshold |
| `AVG_CONFIDENCE_THRESHOLD` | 0.80 | Average confidence threshold |
| `FIELD_COVERAGE_THRESHOLD` | 0.60 | Field coverage threshold |

---

## Project Structure

```
paddleocr-invoice-extractor/
├── app/
│   ├── __init__.py              # Package init
│   ├── config.py                # Configuration (env vars, thresholds, singleton)
│   ├── errors.py                # Business exceptions (unified error codes)
│   ├── schemas.py               # Pydantic data models
│   ├── desensitize.py           # Desensitization tool (masking rules)
│   ├── template.py              # Invoice template (field defs, regions, KV mapping)
│   ├── ocr.py                   # OCR engine (PaddleOCR lazy load, inference)
│   ├── main.py                  # FastAPI entry (routes, dependency injection)
│   └── static/
│       ├── index.html           # Frontend page
│       ├── styles.css           # Stylesheet
│       ├── app.js               # Frontend logic
│       └── icons/               # SVG icons
├── tests/
│   ├── test_config.py           # Configuration tests
│   ├── test_errors.py           # Exception tests
│   ├── test_schemas.py          # Data model tests
│   ├── test_desensitize.py      # Desensitization tool tests
│   ├── test_template.py         # Template tests
│   ├── test_ocr.py              # OCR engine tests
│   ├── test_api.py              # API endpoint tests
│   ├── test_frontend.py         # Frontend page tests
│   ├── test_privacy.py          # Privacy scanner tests
│   └── __init__.py
├── scripts/
│   └── privacy_scan.py          # Privacy scanning script
├── .github/
│   └── workflows/
│       └── tests.yml            # CI workflow
├── pyproject.toml               # Project config and dependencies
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development dependencies
├── .env.example                 # Environment variable example
├── .gitignore                   # Git ignore rules
├── LICENSE                      # MIT License
├── README.md                    # Project docs (Chinese)
└── README_en.md                 # Project docs (English)
```

---

## Contributing

We welcome contributions! Please read the following documents:

- [Contributing Guide (CONTRIBUTING.md)](CONTRIBUTING.md) — Code standards, commit format, PR flow, privacy requirements
- [Code of Conduct (CODE_OF_CONDUCT.md)](CODE_OF_CONDUCT.md) — Community behavior standards
- [Security Policy (SECURITY.md)](SECURITY.md) — Security vulnerability reporting process

This project is open-sourced under the [MIT License](LICENSE).
