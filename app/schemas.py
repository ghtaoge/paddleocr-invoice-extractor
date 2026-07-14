"""票析 — Pydantic 请求/响应模型

所有模型使用 extra="forbid" 保证 API 合约严格——
不接受未声明的字段，防止客户端误传多余数据。"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

# ── 约束类型别名 ──────────────────────────────────────────────
Probability = Annotated[float, Field(ge=0, le=1)]


class ContractModel(BaseModel):
    """API 合约基类——禁止额外字段，防止数据泄漏。"""

    model_config = {"extra": "forbid"}


# ── 字段与分组 ────────────────────────────────────────────────
class InvoiceField(ContractModel):
    """单个发票字段——包含原始值、脱敏值和置信度。"""

    key: str
    label: str
    value: str
    confidence: Probability
    desensitized: str


class FieldGroup(ContractModel):
    """字段分组——如基础信息、金额信息等。"""

    name: str
    fields: list[InvoiceField]


# ── 可靠性评估 ────────────────────────────────────────────────
ReliabilityReason = Literal[
    "字段不完整",
    "识别置信度偏低",
    "模板匹配不足",
]


class Reliability(ContractModel):
    """可靠性评估——level 为 high/low，reasons 列出具体原因。"""

    level: Literal["high", "low"]
    reasons: list[ReliabilityReason]


# ── 识别结果 ──────────────────────────────────────────────────
class InvoiceResult(ContractModel):
    """完整发票识别结果——包含分组字段、整体置信度和可靠性。"""

    groups: list[FieldGroup]
    overall_confidence: Probability
    reliability: Reliability
    device: str
    ocr_boxes: list[dict]  # PaddleOCR 原始检测框，前端标注用
    debug_trace: list[dict] = []  # v2: 诊断追踪——每步匹配细节

    @field_validator("device")
    @classmethod
    def reject_blank_device(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("不能为空白字符串")
        return v


# ── 健康检查 ──────────────────────────────────────────────────
class HealthResponse(ContractModel):
    """健康检查响应。"""

    status: Literal["ok"]
    model_status: Literal["not_loaded", "loading", "loaded", "error"]
    device: str


# ── 公开错误 ──────────────────────────────────────────────────
class PublicError(ContractModel):
    """面向用户的错误——code 供程序判断，message 供用户阅读。"""

    code: str
    message: str

    @field_validator("code", "message")
    @classmethod
    def reject_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("不能为空白字符串")
        return v
