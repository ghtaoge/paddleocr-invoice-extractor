# 票析：PaddleOCR 增值税发票识别

> **声明：本项目为教学案例**，旨在演示 PaddleOCR 与 FastAPI 的集成方式，**不适用于生产环境**。识别结果可能存在偏差，请勿用于实际财务或法律用途。

---

## 项目简介

**票析** 是一个基于 PaddleOCR PP-OCRv4 的增值税发票 OCR 识别教学案例，采用 **区域定位 + 关键词映射** 双策略提取发票结构化字段，并通过 **诚实降级机制** 告知用户识别结果的可靠性。

核心识别流程：

1. **PaddleOCR PP-OCRv4** 执行文字检测与识别，返回文字框坐标、文本和置信度
2. **区域定位** — 根据 OCR 文字框的 y 坐标百分比将文字归入版式区域（基础信息、购方信息、金额信息、销方信息）
3. **关键词映射** — 在对应区域内搜索特征关键词，将关键词附近文字框的值作为字段值
4. **诚实降级** — 三项检查评估可靠性：
   - 关键字段缺失率 > **30%** → 标记 `字段不完整`
   - 平均置信度 < **0.80** → 标记 `识别置信度偏低`
   - 字段覆盖率 < **60%** → 标记 `模板匹配不足`
   - 任一触发 → `reliability.level = "low"`，否则 `"high"`

---

## 功能

- 增值税发票图片 OCR 识别（JPG / PNG / BMP）
- 16 个关键字段提取，按 4 组分类展示：基础信息、金额信息、购方信息、销方信息
- 诚实降级机制 — 低可靠度结果明确标注原因，不误导用户
- 脱敏展示 — 公司名称、税号、发票号码、金额等敏感字段默认遮蔽，可逐字段揭示
- 原图标注 — 在原图上绘制 OCR 检测框，可视化识别区域
- JSON / CSV 导出 — 导出文件保留完整数据，前端展示使用脱敏版本
- 健康检查 — 实时查看模型加载状态与推理设备
- 并发控制 — 同一时间只处理一个请求，防止资源争用
- 纯本地运行 — 不上传任何数据至第三方服务器，识别完毕即从内存清除
- 隐私扫描 — CI 自动检测代码仓库中的敏感信息泄漏风险

---

## 技术架构

```
┌─────────────── 前端 (index.html + app.js) ────────────────┐
│  拖拽上传 → /api/ocr → 结构化表格 / 原图标注 / 脱敏展示    │
│  健康状态轮询 → /api/health → 状态栏指示灯                 │
└────────────────────────┬────────────────────────────────────┘
                         │ multipart/form-data
                         ▼
┌─────────────── FastAPI (app/main.py) ──────────────────────┐
│  并发锁 · 文件校验 · 格式校验 · 异常处理                     │
│  Services 容器: OCRRunner + InvoiceTemplate                 │
└────────────────────────┬────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
┌───── OCRRunner ──────┐  ┌── InvoiceTemplate ──┐
│  PaddleOCR PP-OCRv4  │  │  区域定位 (y%)      │
│  懒加载 · 单例 · GPU  │  │  关键词映射          │
│  自动检测设备         │  │  脱敏 (desensitize) │
└───────────────────────┘  │  可靠性评估          │
                           └─────────────────────┘
```

### 模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 配置 | `app/config.py` | 环境变量加载、阈值约束、进程级单例 |
| OCR 引擎 | `app/ocr.py` | PaddleOCR 懒加载、设备检测、推理调用 |
| 发票模板 | `app/template.py` | 字段定义、区域划分、KV 映射、可靠性评估 |
| 脱敏工具 | `app/desensitize.py` | 公司名称/税号/发票号码/金额遮蔽规则 |
| 数据模型 | `app/schemas.py` | Pydantic 请求/响应模型，`extra="forbid"` 严格合约 |
| 异常定义 | `app/errors.py` | 统一业务异常，code + 中文 message + HTTP 状态码 |
| 应用入口 | `app/main.py` | 路由注册、依赖注入、静态文件挂载 |
| 隐私扫描 | `scripts/privacy_scan.py` | CI 隐私泄漏检测（私钥、Token、真实公司名、二进制文件） |

### 设计原则

- **诚实降级** — 不隐藏低置信度结果，明确告知原因
- **最小暴露** — API 合约 `extra="forbid"`，异常只暴露 code 和 public_message
- **本地优先** — 所有数据在本地处理，不上传第三方服务器
- **默认脱敏** — 前端默认展示遮蔽值，逐字段揭示，导出保留完整数据
- **依赖注入** — 工厂模式 `create_app()`，测试注入假服务，生产注入真实服务

---

## API 接口

### GET /

返回主页面（`index.html`）。

### GET /api/health

健康检查——返回服务状态、模型加载状态和推理设备。

**响应示例：**

```json
{
  "status": "ok",
  "model_status": "loaded",
  "device": "cpu"
}
```

| model_status | 含义 |
|---|---|
| `not_loaded` | 模型尚未加载（首次启动时） |
| `loading` | 模型正在加载 |
| `loaded` | 模型已加载，可正常识别 |
| `error` | 模型加载失败 |

### POST /api/ocr

发票识别——上传图片文件，返回结构化字段结果。

**请求：** `multipart/form-data`，字段名 `file`，支持 JPG / PNG / BMP，最大 10 MB。

**响应示例：**

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

**低可靠度响应示例：**

```json
{
  "reliability": {
    "level": "low",
    "reasons": ["字段不完整", "识别置信度偏低"]
  }
}
```

### 错误码

| HTTP 状态码 | code | message | 触发条件 |
|---|---|---|---|
| 413 | `FILE_TOO_LARGE` | 上传文件超过大小限制 | 文件超过 10 MB |
| 415 | `UNSUPPORTED_FORMAT` | 不支持该图片格式 | 非 JPG/PNG/BMP |
| 422 | `NO_TEXT_DETECTED` | 图片中未检测到文字 | OCR 未检测到任何文字 |
| 422 | `OCR_FAILED` | 图片识别失败，请确认图片清晰度 | PaddleOCR 推理异常 |
| 429 | `CONCURRENT_REQUEST` | 正在处理中，请稍后再试 | 重复并发请求 |
| 500 | `INTERNAL_ERROR` | 服务内部错误 | 未预期的内部异常 |

---

## 环境要求

- Python >= 3.11, < 3.14
- PaddlePaddle >= 3.0（CPU 版本默认；GPU 版本需 CUDA 环境）
- 操作系统：Windows / Linux / macOS

---

## 安装

```bash
# 克隆仓库
git clone https://github.com/Gooeto/paddleocr-invoice-extractor.git
cd paddleocr-invoice-extractor

# 创建虚拟环境（推荐）
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖（可选，用于测试和 lint）
pip install -r requirements-dev.txt
```

首次识别时，PaddleOCR 会自动下载 PP-OCRv4 模型权重（约 10 MB），后续识别复用本地缓存。

---

## 启动

```bash
# 开发模式启动（自动重载）
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 生产模式启动
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后浏览器访问 `http://127.0.0.1:8000` 即可使用。

可通过环境变量或 `.env` 文件覆盖默认配置（参考 `.env.example`）：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `HOST` | `127.0.0.1` | 监听地址 |
| `PORT` | `8000` | 监听端口 |
| `MAX_FILE_BYTES` | `10485760` | 上传文件大小上限（字节） |
| `OCR_USE_GPU` | `false` | 是否使用 GPU 推理 |

---

## 测试

```bash
# 运行单元测试
python -m pytest -q

# 运行测试并输出覆盖率
python -m pytest --cov=app --cov-report=term-missing

# 代码格式检查
python -m ruff format --check app tests scripts
python -m ruff check app tests scripts

# 自动格式修正
python -m ruff format app tests scripts
python -m ruff check --fix app tests scripts

# 隐私扫描（检测仓库中的敏感信息泄漏）
python scripts/privacy_scan.py

# 类型检查
python -m mypy app
```

CI 自动执行：ruff format/check → privacy_scan → pytest（参见 `.github/workflows/tests.yml`）。

---

## 隐私

- **纯本地运行** — 所有 OCR 推理在本地完成，不上传图片至任何第三方服务器
- **无数据库** — 不存储任何发票数据，识别完毕即从内存清除
- **默认脱敏** — 前端展示时对敏感字段进行遮蔽处理（公司名称、税号、发票号码、金额）
- **逐字段揭示** — 用户可点击逐个查看完整值，避免一次性暴露所有敏感数据
- **导出双轨** — 前端展示脱敏版本，导出文件保留完整数据，用户自主选择
- **隐私扫描** — CI 自动检测代码仓库中的私钥、Token、真实公司名称和二进制文件

---

## 模板与字段

增值税发票模板定义 16 个关键字段，按 4 组分类：

| 字段组 | 字段 | 中文标签 | 关键词 |
|---|---|---|---|
| 基础信息 | `invoice_code` | 发票代码 | 发票代码、代码 |
| 基础信息 | `invoice_number` | 发票号码 | 发票号码、号码、No |
| 基础信息 | `invoice_date` | 开票日期 | 开票日期、日期 |
| 基础信息 | `check_code` | 校验码 | 校验码 |
| 金额信息 | `amount_without_tax` | 不含税金额 | 合计、金额、不含税 |
| 金额信息 | `tax_rate` | 税率 | 税率 |
| 金额信息 | `tax_amount` | 税额 | 税额 |
| 金额信息 | `amount_with_tax` | 价税合计 | 价税合计、合计 |
| 购方信息 | `buyer_name` | 购方名称 | 购方名称、购买方、名称 |
| 购方信息 | `buyer_tax_number` | 购方纳税人识别号 | 购方纳税人识别号、购方识别号、纳税人识别号 |
| 购方信息 | `buyer_address_phone` | 购方地址、电话 | 购方地址、地址电话、地址、电话 |
| 购方信息 | `buyer_bank_account` | 购方开户行及账号 | 购方开户行、开户行及账号、开户行 |
| 销方信息 | `seller_name` | 销方名称 | 销方名称、销售方、名称 |
| 销方信息 | `seller_tax_number` | 销方纳税人识别号 | 销方纳税人识别号、销方识别号 |
| 销方信息 | `seller_address_phone` | 销方地址、电话 | 销方地址 |
| 销方信息 | `seller_bank_account` | 销方开户行及账号 | 销方开户行 |

区域划分（按发票版式 y 坐标百分比）：

| 区域 | y 范围 | 对应字段组 |
|---|---|---|
| header | 0% – 15% | — |
| basic_info | 15% – 28% | 基础信息 |
| buyer_info | 28% – 45% | 购方信息 |
| item_detail | 45% – 62% | —（不提取） |
| amount_info | 62% – 75% | 金额信息 |
| seller_info | 75% – 90% | 销方信息 |
| footer | 90% – 100% | —（不提取） |

---

## 常见问题

### 首次启动很慢？

首次识别时 PaddleOCR 需要下载 PP-OCRv4 模型权重（约 10 MB），下载速度取决于网络环境。后续识别复用本地缓存，无需重复下载。

### GPU 推理如何启用？

设置环境变量 `OCR_USE_GPU=true`，并确保已安装 CUDA 版本的 PaddlePaddle。系统会自动检测设备：

```bash
# 安装 GPU 版本 PaddlePaddle（需 CUDA 环境）
pip install paddlepaddle-gpu

# 启动时设置环境变量
OCR_USE_GPU=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 识别准确率不高？

本项目为教学案例，采用区域定位 + 关键词映射的简单策略，存在以下局限：

- 非标准版式发票的区域划分可能不准确
- 关键词匹配可能误匹配相近关键词
- 图片模糊、倾斜、遮挡会显著降低识别准确率

请查看 `reliability.level` 和 `reliability.reasons` 评估结果可信度。

### 为什么同时只能处理一个请求？

服务使用线程锁限制并发为 1，因为 PaddleOCR 推理占用较大内存，并发可能导致资源争用。如需多并发，请部署多实例并使用反向代理负载均衡。

### 如何调整可靠性阈值？

通过环境变量覆盖默认阈值（参考 `app/config.py`）：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `FIELD_MISSING_RATIO_THRESHOLD` | 0.30 | 字段缺失率阈值 |
| `AVG_CONFIDENCE_THRESHOLD` | 0.80 | 平均置信度阈值 |
| `FIELD_COVERAGE_THRESHOLD` | 0.60 | 字段覆盖率阈值 |

---

## 项目结构

```
paddleocr-invoice-extractor/
├── app/
│   ├── __init__.py              # 包初始化
│   ├── config.py                # 配置（环境变量、阈值、单例）
│   ├── errors.py                # 业务异常（统一错误码）
│   ├── schemas.py               # Pydantic 数据模型
│   ├── desensitize.py           # 脱敏工具（遮蔽规则）
│   ├── template.py              # 发票模板（字段定义、区域划分、KV 映射）
│   ├── ocr.py                   # OCR 引擎（PaddleOCR 懒加载、推理）
│   ├── main.py                  # FastAPI 入口（路由、依赖注入）
│   └── static/
│       ├── index.html           # 前端页面
│       ├── styles.css           # 样式表
│       ├── app.js               # 前端逻辑
│       └── icons/               # SVG 图标
├── tests/
│   ├── test_config.py           # 配置测试
│   ├── test_errors.py           # 异常测试
│   ├── test_schemas.py          # 数据模型测试
│   ├── test_desensitize.py      # 脱敏工具测试
│   ├── test_template.py         # 模板测试
│   ├── test_ocr.py              # OCR 引擎测试
│   ├── test_api.py              # API 端点测试
│   ├── test_frontend.py         # 前端页面测试
│   ├── test_privacy.py          # 隐私扫描测试
│   └── __init__.py
├── scripts/
│   └── privacy_scan.py          # 隐私扫描脚本
├── .github/
│   └── workflows/
│       └── tests.yml            # CI 工作流
├── pyproject.toml               # 项目配置与依赖
├── requirements.txt             # 生产依赖
├── requirements-dev.txt         # 开发依赖
├── .env.example                 # 环境变量示例
├── .gitignore                   # Git 忽略规则
├── LICENSE                      # MIT 许可证
├── README.md                    # 项目文档（中文）
└── README_en.md                 # 项目文档（英文）
```

---

## 开源协作

欢迎参与贡献！请阅读以下文档：

- [贡献指南 (CONTRIBUTING.md)](CONTRIBUTING.md) — 代码规范、提交格式、PR 流程、隐私要求
- [行为准则 (CODE_OF_CONDUCT.md)](CODE_OF_CONDUCT.md) — 社区行为规范
- [安全政策 (SECURITY.md)](SECURITY.md) — 安全漏洞报告流程

项目采用 [MIT 许可证](LICENSE) 开源。
