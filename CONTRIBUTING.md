# 贡献指南

感谢你对票析项目的关注！本文档描述代码规范、提交格式、PR 流程和隐私要求。

---

## 代码规范

### Lint 与格式

项目使用 [ruff](https://docs.astral.sh/ruff/) 进行代码格式化和 lint 检查。

```bash
# 格式化
python -m ruff format app tests scripts

# Lint 检查
python -m ruff check app tests scripts

# 自动修复 lint 问题
python -m ruff check --fix app tests scripts
```

配置详见 `pyproject.toml` 中 `[tool.ruff]` 部分：

- 行宽上限：100 字符
- 目标版本：Python 3.11
- 启用规则：E, F, I, B, UP, SIM, RUF（忽略 RUF001/002/003，允许中文字符）

### 中文注释

代码注释使用中文。函数和类的 docstring 应包含中文说明，参数和返回值描述使用中文。

```python
def desensitize_invoice_number(value: str) -> str:
    """发票号码脱敏——中间 4 位遮蔽。

    示例：12345678 → 12****78（至少 8 位时遮蔽中间 4 位）
    短于 4 位的值不做遮蔽。
    """
```

### 单元测试

每个模块必须包含对应的单元测试。测试文件位于 `tests/` 目录，命名格式 `test_<module>.py`。

```bash
# 运行全部测试
python -m pytest -q

# 运行单个模块测试
python -m pytest tests/test_desensitize.py -q

# 运行测试并输出覆盖率
python -m pytest --cov=app --cov-report=term-missing
```

测试要求：

- 使用 pytest 框架
- 测试类使用 `class Test*` 命名
- 测试方法使用 `def test_*` 命名
- API 测试注入假服务（`FakeOCRRunner`），不依赖真实 PaddleOCR 模型

---

## 提交格式

使用 Conventional Commits 格式：

```
type: description
```

### 类型（type）

| type | 说明 |
|---|---|
| `feat` | 新功能 |
| `fix` | 修复 bug |
| `docs` | 文档变更 |
| `style` | 代码格式调整（不影响逻辑） |
| `refactor` | 代码重构（不新增功能、不修复 bug） |
| `test` | 测试相关 |
| `chore` | 构建、配置、工具等杂项 |
| `perf` | 性能优化 |

### 示例

```
feat: 增加发票类型自动检测
fix: 修复区域定位在非标准版式下的偏移问题
docs: 更新 API 接口文档
test: 增加脱敏工具边界值测试
chore: 更新 ruff 版本到 0.9
```

---

## PR 流程

1. **Fork** 仓库到你的 GitHub 账号
2. 从 `main` 分支创建功能分支：`git checkout -b feat/my-feature`
3. 编写代码和测试，确保所有测试通过：
   ```bash
   python -m ruff format --check app tests scripts
   python -m ruff check app tests scripts
   python scripts/privacy_scan.py
   python -m pytest -q
   ```
4. 提交代码，使用规范的提交格式
5. 推送分支并创建 Pull Request，目标分支为 `main`
6. PR 描述应包含：
   - 变更目的和背景
   - 主要修改内容
   - 测试覆盖说明
   - 是否涉及敏感数据处理

### PR 检查清单

- [ ] ruff format/check 通过
- [ ] 隐私扫描通过（`python scripts/privacy_scan.py`）
- [ ] 全部测试通过（`python -m pytest -q`）
- [ ] 新代码有对应的单元测试
- [ ] 不包含真实发票数据、真实公司名称或敏感信息
- [ ] 提交格式符合 Conventional Commits 规范

---

## 隐私要求

本项目处理增值税发票数据，隐私保护是首要要求。

### 禁止提交的内容

- **真实发票图片** — 任何包含真实发票内容的 JPG/PNG/BMP 文件
- **真实公司名称** — 如"北京某某科技有限公司"这类占位符名称可以使用，但不能使用真实注册的公司名称
- **真实纳税人识别号** — 使用虚构的示例税号（如 `91110000MA01ABCDEF`）
- **真实发票号码/代码** — 使用虚构的示例编号（如 `12345678`）
- **PEM 私钥** — 任何格式的私钥文件
- **Bearer Token** — 任何认证令牌
- **用户路径** — Windows 用户路径（如 `C:\Users\realname`）或 POSIX 用户路径

### 安全使用占位数据

测试中使用虚构数据：

```python
# 正确：使用虚构的示例数据
invoice_number = "12345678"  # 示例号码
company_name = "北京某某科技有限公司"  # 占位符名称

# 错误：使用真实数据
# invoice_number = "3200XXXXXX"  # 真实发票号码
# company_name = "北京真实公司名称有限公司"  # 真实公司名称
```

### 隐私扫描

每次 PR 都会自动运行隐私扫描脚本。你也可以手动运行：

```bash
python scripts/privacy_scan.py
```

扫描检测：

- 禁止提交的二进制文件（图片、模型权重等）
- PEM 格式私钥
- Bearer Token
- Windows/POSIX 用户路径泄漏
- 真实公司名称（增值税发票特有风险）

如果扫描发现风险，PR 将无法合并。文档文件（README.md、README_en.md、CONTRIBUTING.md、SECURITY.md）中的示例数据已排除在扫描范围外。

---

## 开发环境搭建

```bash
# 克隆仓库
git clone https://github.com/Gooeto/paddleocr-invoice-extractor.git
cd paddleocr-invoice-extractor

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 安装开发依赖
pip install -r requirements-dev.txt
```

---

## 问题反馈

如果你发现问题或有建议，请通过 GitHub Issues 提交。问题描述应包含：

- 问题现象和复现步骤
- 期望行为
- 实际行为
- 环境信息（Python 版本、操作系统、是否使用 GPU）
