"""测试 Pydantic 模型合约——字段约束、序列化、禁止额外字段。"""

import pytest
from pydantic import ValidationError

from app.schemas import (
    FieldGroup,
    HealthResponse,
    InvoiceField,
    InvoiceResult,
    PublicError,
    Reliability,
)


class TestInvoiceField:
    """发票字段模型。"""

    def test_valid_field(self) -> None:
        f = InvoiceField(
            key="invoice_number",
            label="发票号码",
            value="12345678",
            confidence=0.95,
            desensitized="12****78",
        )
        assert f.key == "invoice_number"

    def test_reject_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceField(
                key="invoice_number",
                label="发票号码",
                value="12345678",
                confidence=0.95,
                desensitized="12****78",
                extra="不应该出现",  # type: ignore[call-arg]
            )

    def test_confidence_range(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceField(
                key="test",
                label="测试",
                value="val",
                confidence=1.5,  # 超出 [0, 1]
                desensitized="val",
            )


class TestFieldGroup:
    """字段分组模型。"""

    def test_valid_group(self) -> None:
        g = FieldGroup(
            name="基础信息",
            fields=[
                InvoiceField(
                    key="invoice_code",
                    label="发票代码",
                    value="1234",
                    confidence=0.90,
                    desensitized="1234",
                )
            ],
        )
        assert g.name == "基础信息"
        assert len(g.fields) == 1


class TestReliability:
    """可靠性模型。"""

    def test_high_reliability(self) -> None:
        r = Reliability(level="high", reasons=[])
        assert r.level == "high"

    def test_low_reliability(self) -> None:
        r = Reliability(level="low", reasons=["字段不完整"])
        assert r.level == "low"

    def test_reject_invalid_level(self) -> None:
        with pytest.raises(ValidationError):
            Reliability(level="medium", reasons=[])


class TestInvoiceResult:
    """完整结果模型。"""

    def test_reject_blank_device(self) -> None:
        with pytest.raises(ValidationError, match="不能为空白字符串"):
            InvoiceResult(
                groups=[],
                overall_confidence=0.9,
                reliability=Reliability(level="high", reasons=[]),
                device="   ",
                ocr_boxes=[],
            )


class TestHealthResponse:
    """健康检查模型。"""

    def test_valid_response(self) -> None:
        h = HealthResponse(status="ok", model_status="loaded", device="cpu")
        assert h.status == "ok"

    def test_reject_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            HealthResponse(status="error", model_status="loaded", device="cpu")


class TestPublicError:
    """公开错误模型。"""

    def test_valid_error(self) -> None:
        e = PublicError(code="TEST", message="测试错误")
        assert e.code == "TEST"

    def test_reject_blank_code(self) -> None:
        with pytest.raises(ValidationError):
            PublicError(code="   ", message="msg")

    def test_reject_blank_message(self) -> None:
        with pytest.raises(ValidationError):
            PublicError(code="CODE", message="   ")
