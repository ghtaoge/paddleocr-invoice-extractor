"""测试增值税发票模板——区域定位、关键词匹配、可靠性评估。"""

import pytest

from app.config import Settings
from app.schemas import FieldGroup, InvoiceField, Reliability
from app.template import (
    FIELD_DEFINITIONS,
    InvoiceTemplate,
    REGIONS,
    _classify_region,
    evaluate_reliability,
)


class TestClassifyRegion:
    """区域定位——根据 y 坐标百分比判断版式区域。"""

    def test_basic_info_region(self) -> None:
        assert _classify_region(0.20, 1.0) == "basic_info"

    def test_buyer_info_region(self) -> None:
        assert _classify_region(0.35, 1.0) == "buyer_info"

    def test_amount_info_region(self) -> None:
        assert _classify_region(0.68, 1.0) == "amount_info"

    def test_seller_info_region(self) -> None:
        assert _classify_region(0.82, 1.0) == "seller_info"

    def test_header_region(self) -> None:
        assert _classify_region(0.08, 1.0) == "header"

    def test_footer_region(self) -> None:
        assert _classify_region(0.95, 1.0) == "footer"


class TestFieldDefinitions:
    """字段定义完整性检查。"""

    def test_all_groups_present(self) -> None:
        groups = {d["group"] for d in FIELD_DEFINITIONS.values()}
        assert "基础信息" in groups
        assert "金额信息" in groups
        assert "购方信息" in groups
        assert "销方信息" in groups

    def test_total_field_count(self) -> None:
        assert len(FIELD_DEFINITIONS) == 16


class TestInvoiceTemplate:
    """模板映射——将 OCR 结果映射为结构化字段。"""

    def test_empty_ocr_results(self) -> None:
        template = InvoiceTemplate()
        groups = template.map_results([], image_height=1000)
        # 应返回 4 个空分组
        assert len(groups) == 4
        assert all(len(g.fields) == 0 for g in groups)

    def test_single_keyword_match(self) -> None:
        """关键词"发票号码"出现在基础信息区，其后紧跟号码值。"""
        template = InvoiceTemplate()
        # 模拟 OCR 结果：关键词在基础信息区 (y ≈ 0.20 * 1000 = 200)
        ocr_results = [
            ((100, 200, 200, 220), "发票号码", 0.98),
            ((210, 200, 300, 220), "12345678", 0.95),
        ]
        groups = template.map_results(ocr_results, image_height=1000)
        basic_group = groups[0]  # 基础信息
        found = any(f.key == "invoice_number" for f in basic_group.fields)
        assert found

    def test_keyword_in_wrong_region(self) -> None:
        """关键词出现在错误区域时不应匹配。"""
        template = InvoiceTemplate()
        # "销方名称"关键词出现在购方区 (y ≈ 350, 在 buyer_info 区)
        # 但销方名称的 expected_region 是 seller_info
        ocr_results = [
            ((100, 350, 200, 370), "销方名称", 0.98),
            ((210, 350, 300, 370), "某公司", 0.95),
        ]
        groups = template.map_results(ocr_results, image_height=1000)
        seller_group = groups[3]  # 销方信息
        assert len(seller_group.fields) == 0

    def test_multiple_fields_in_same_region(self) -> None:
        """同一区域内多个关键词应分别匹配。"""
        template = InvoiceTemplate()
        # 基础信息区有多个字段
        ocr_results = [
            ((10, 200, 100, 220), "发票代码", 0.97),
            ((110, 200, 200, 220), "044001900111", 0.96),
            ((10, 230, 100, 250), "发票号码", 0.98),
            ((110, 230, 200, 250), "12345678", 0.95),
        ]
        groups = template.map_results(ocr_results, image_height=1000)
        basic_group = groups[0]  # 基础信息
        assert len(basic_group.fields) >= 1  # 至少匹配到一个


class TestEvaluateReliability:
    """可靠性评估——诚实降级机制。"""

    def test_high_reliability(self) -> None:
        """所有字段都提取到、置信度高 → high。"""
        fields = [
            InvoiceField(
                key=f"field_{i}",
                label=f"字段{i}",
                value=f"val{i}",
                confidence=0.95,
                desensitized=f"val{i}",
            )
            for i in range(16)  # 全部 16 个字段
        ]
        groups = [FieldGroup(name="测试", fields=fields)]
        settings = Settings()
        result = evaluate_reliability(groups, settings)
        assert result.level == "high"

    def test_low_reliability_missing_fields(self) -> None:
        """缺失率高 → low + "字段不完整"。"""
        groups = [FieldGroup(name="基础信息", fields=[])]
        settings = Settings()
        result = evaluate_reliability(groups, settings)
        assert result.level == "low"
        assert "字段不完整" in result.reasons

    def test_low_reliability_low_confidence(self) -> None:
        """置信度低 → low + "识别置信度偏低"。"""
        # 生成足够多的低置信度字段使平均值低于 0.80
        low_conf_fields = [
            InvoiceField(
                key=f"field_{i}",
                label=f"字段{i}",
                value=f"val{i}",
                confidence=0.50,
                desensitized=f"val{i}",
            )
            for i in range(10)
        ]
        groups = [FieldGroup(name="测试", fields=low_conf_fields)]
        settings = Settings()
        result = evaluate_reliability(groups, settings)
        assert "识别置信度偏低" in result.reasons
