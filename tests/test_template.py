"""测试增值税发票模板——区域定位、关键词匹配、可靠性评估。

v3 测试更新：
- map_results 返回 (groups, debug_trace) tuple
- 移除已删除函数的导入（_classify_primary_region, _is_below_keyword, _is_on_same_line）
- 新增 nearby 搜索模式测试（金额/购方/销方不再要求同行）
- 新增 debug_trace 验证"""

from app.config import Settings
from app.schemas import FieldGroup, InvoiceField
from app.template import (
    FIELD_DEFINITIONS,
    GROUP_REGION_MAP,
    InvoiceTemplate,
    _classify_region,
    _clean_value,
    _is_valid_value,
    _spatial_distance,
    evaluate_reliability,
)


def _call_map(template, ocr_results, image_height=1000):
    """辅助函数——调用 map_results 并返回 groups（忽略 trace）。"""
    groups, trace = template.map_results(ocr_results, image_height=image_height)
    return groups


class TestClassifyRegion:
    """区域定位——根据 y 坐标百分比判断版式区域。"""

    def test_basic_info_region(self) -> None:
        regions = _classify_region(0.20, 1.0)
        assert "basic_info" in regions

    def test_buyer_info_region(self) -> None:
        regions = _classify_region(0.35, 1.0)
        assert "buyer_info" in regions

    def test_amount_info_region(self) -> None:
        regions = _classify_region(0.68, 1.0)
        assert "amount_info" in regions

    def test_seller_info_region(self) -> None:
        regions = _classify_region(0.82, 1.0)
        assert "seller_info" in regions

    def test_header_region(self) -> None:
        regions = _classify_region(0.08, 1.0)
        assert "header" in regions

    def test_footer_region(self) -> None:
        regions = _classify_region(0.95, 1.0)
        assert "footer" in regions

    def test_overlap_boundary_basic_buyer(self) -> None:
        """边界附近应匹配多个区域。"""
        regions = _classify_region(0.25, 1.0)
        assert len(regions) >= 2
        assert "basic_info" in regions
        assert "buyer_info" in regions


class TestSpatialDistance:
    """空间距离计算——综合水平+垂直偏移。"""

    def test_right_same_line_close(self) -> None:
        """右侧同行近距离→小距离（无左侧惩罚）。"""
        kw = (10, 100, 110, 120)
        cand = (120, 100, 220, 120)
        dist = _spatial_distance(kw, cand)
        # 无左侧惩罚，只有水平距离（~15）和垂直距离（0）
        assert dist < 150

    def test_below_keyword(self) -> None:
        """下方1行→中等距离（垂直距离权重0.3）。"""
        kw = (10, 100, 110, 120)
        cand = (10, 140, 200, 160)  # 下方40px
        dist = _spatial_distance(kw, cand)
        # 水平偏移 ≈50px + 垂直40*0.3=12 → ≈62
        assert dist < 100

    def test_left_side_penalty(self) -> None:
        """左侧候选框→大幅惩罚（+100）。"""
        kw = (200, 100, 300, 120)
        cand = (50, 100, 150, 120)  # 在关键词左侧
        dist = _spatial_distance(kw, cand)
        assert dist >= 100


class TestCleanValue:
    """值清洗——移除常见前缀后缀。"""

    def test_yuan_prefix(self) -> None:
        assert _clean_value("¥1234.56") == "1234.56"

    def test_chinese_yuan_prefix(self) -> None:
        assert _clean_value("￥1234.56") == "1234.56"

    def test_yuan_suffix(self) -> None:
        assert _clean_value("1234.56元") == "1234.56"

    def test_yuan_suffix_with_paren(self) -> None:
        assert _clean_value("1234.56元)") == "1234.56"

    def test_colon_prefix(self) -> None:
        assert _clean_value("：1234") == "1234"

    def test_plain_value(self) -> None:
        assert _clean_value("12345678") == "12345678"

    def test_spaces(self) -> None:
        assert _clean_value("  1234  ") == "1234"


class TestFieldDefinitions:
    """字段定义完整性检查。"""

    def test_all_groups_present(self) -> None:
        groups = {d["group"] for d in FIELD_DEFINITIONS.values()}
        assert "基础信息" in groups
        assert "金额信息" in groups
        assert "购方信息" in groups
        assert "销方信息" in groups

    def test_total_field_count(self) -> None:
        # v8: 新增出行信息7个字段 → 31
        assert len(FIELD_DEFINITIONS) == 31

    def test_group_region_map(self) -> None:
        assert GROUP_REGION_MAP["基础信息"] == "basic_info"
        assert GROUP_REGION_MAP["购方信息"] == "buyer_info"
        assert GROUP_REGION_MAP["金额信息"] == "amount_info"
        assert GROUP_REGION_MAP["销方信息"] == "seller_info"

    def test_search_modes(self) -> None:
        """金额/购方/销方字段使用 'nearby' 搜索模式。"""
        nearby_fields = [
            k for k, d in FIELD_DEFINITIONS.items() if d.get("search_mode") == "nearby"
        ]
        assert "amount_without_tax" in nearby_fields
        assert "buyer_name" in nearby_fields
        assert "seller_name" in nearby_fields

    def test_basic_info_search_modes(self) -> None:
        """基础信息字段使用 'right' 搜索模式。"""
        right_fields = [k for k, d in FIELD_DEFINITIONS.items() if d.get("search_mode") == "right"]
        assert "invoice_code" in right_fields
        assert "invoice_number" in right_fields


class TestInvoiceTemplate:
    """模板映射——将 OCR 结果映射为结构化字段。"""

    def test_empty_ocr_results(self) -> None:
        template = InvoiceTemplate()
        groups, trace = template.map_results([], image_height=1000)
        # v8: 6个分组（基础信息、金额信息、购方信息、销方信息、出行信息、其他信息）
        assert len(groups) == 6
        assert all(len(g.fields) == 0 for g in groups)

    def test_returns_debug_trace(self) -> None:
        """v3: map_results 返回 debug_trace。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 200, 120, 220), "发票号码", 0.98),
            ((130, 200, 220, 220), "12345678", 0.95),
        ]
        groups, trace = template.map_results(ocr_results, image_height=1000)
        assert isinstance(trace, list)
        assert len(trace) > 0
        # 第一个 trace 条目应该是 OCR 原始数据
        assert trace[0]["step"] == "ocr_raw"

    def test_keyword_and_value_separate(self) -> None:
        """关键词和值分开识别——同行右侧。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 200, 120, 220), "发票号码", 0.98),
            ((130, 200, 220, 220), "12345678", 0.95),
        ]
        groups = _call_map(template, ocr_results)
        basic_group = groups[0]
        found = any(f.key == "invoice_number" for f in basic_group.fields)
        assert found
        inv_num = next(f for f in basic_group.fields if f.key == "invoice_number")
        assert inv_num.value == "12345678"

    def test_keyword_and_value_combined(self) -> None:
        """关键词和值合并识别——如 "发票号码12345678"。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 200, 300, 220), "发票号码12345678", 0.97),
        ]
        groups = _call_map(template, ocr_results)
        basic_group = groups[0]
        found = any(f.key == "invoice_number" for f in basic_group.fields)
        assert found
        inv_num = next(f for f in basic_group.fields if f.key == "invoice_number")
        assert inv_num.value == "12345678"

    def test_keyword_outside_expected_region_still_matches(self) -> None:
        """关键词不在期望区域时仍可匹配（兜底策略）。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((100, 350, 200, 370), "销方名称", 0.98),
            ((210, 350, 300, 370), "某公司", 0.95),
        ]
        groups = _call_map(template, ocr_results)
        seller_group = groups[3]
        found = any(f.key == "seller_name" for f in seller_group.fields)
        assert found, "v3 应该允许关键词在非期望区域匹配（兜底策略）"

    def test_keyword_in_correct_region_priority(self) -> None:
        """关键词在正确区域时优先匹配。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((100, 350, 200, 370), "购方名称", 0.98),
            ((210, 350, 300, 370), "某购方公司", 0.95),
        ]
        groups = _call_map(template, ocr_results)
        buyer_group = groups[2]
        found = any(f.key == "buyer_name" for f in buyer_group.fields)
        assert found

    def test_multiple_fields_in_same_region(self) -> None:
        """同一区域内多个关键词-值对应分别匹配。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((10, 200, 100, 220), "发票代码", 0.97),
            ((110, 200, 200, 220), "044001900111", 0.96),
            ((10, 230, 100, 250), "发票号码", 0.98),
            ((110, 230, 200, 250), "12345678", 0.95),
        ]
        groups = _call_map(template, ocr_results)
        basic_group = groups[0]
        assert len(basic_group.fields) >= 2

    def test_value_with_colon_separator(self) -> None:
        """关键词后带冒号——如 "发票号码：12345678"。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 200, 300, 220), "发票号码：12345678", 0.97),
        ]
        groups = _call_map(template, ocr_results)
        basic_group = groups[0]
        if any(f.key == "invoice_number" for f in basic_group.fields):
            inv_num = next(f for f in basic_group.fields if f.key == "invoice_number")
            assert inv_num.value == "12345678"

    def test_amount_nearby_search_below_keyword(self) -> None:
        """v3: 金额在关键词下方1行——nearby 搜索模式。"""
        template = InvoiceTemplate()
        # "价税合计" 关键词在 y=650，值 "¥1234.56" 在 y=680（下方30px）
        # v2/v1 要求同行右侧，会找不到；v3 nearby 搜索允许下方
        ocr_results = [
            ((30, 650, 150, 670), "价税合计", 0.95),
            ((160, 680, 250, 700), "¥1234.56", 0.93),  # 下方30px
        ]
        groups = _call_map(template, ocr_results)
        amount_group = groups[1]
        found = any(f.key == "amount_with_tax" for f in amount_group.fields)
        assert found, "v3 nearby 搜索应能找到下方30px的金额"

    def test_amount_with_yuan_prefix(self) -> None:
        """金额带 ¥ 前缀——value_pattern 放宽。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 650, 150, 680), "价税合计", 0.95),
            ((160, 650, 250, 680), "¥1234.56", 0.93),
        ]
        groups = _call_map(template, ocr_results)
        amount_group = groups[1]
        found = any(f.key == "amount_with_tax" for f in amount_group.fields)
        assert found
        amt = next(f for f in amount_group.fields if f.key == "amount_with_tax")
        assert amt.value == "1234.56"

    def test_amount_with_comma_separator(self) -> None:
        """金额带逗号分隔——如 "1,234.56"。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 650, 150, 680), "不含税金额", 0.95),
            ((160, 650, 250, 680), "1,234.56", 0.93),
        ]
        groups = _call_map(template, ocr_results)
        amount_group = groups[1]
        found = any(f.key == "amount_without_tax" for f in amount_group.fields)
        assert found

    def test_buyer_name_keyword_variants(self) -> None:
        """v8: 购方名称关键词变体——"购买方名称"（移除了贪心短关键词"购买方"）。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 330, 150, 350), "购买方名称", 0.95),
            ((160, 330, 300, 350), "北京某科技公司", 0.90),
        ]
        groups = _call_map(template, ocr_results)
        buyer_group = groups[2]
        found = any(f.key == "buyer_name" for f in buyer_group.fields)
        assert found

    def test_seller_name_keyword_variants(self) -> None:
        """v8: 销方名称关键词变体——"销售方名称"（移除了贪心短关键词"销售方"）。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 780, 150, 800), "销售方名称", 0.95),
            ((160, 780, 300, 800), "上海某贸易公司", 0.90),
        ]
        groups = _call_map(template, ocr_results)
        seller_group = groups[3]
        found = any(f.key == "seller_name" for f in seller_group.fields)
        assert found


class TestEvaluateReliability:
    """可靠性评估——诚实降级机制。"""

    def test_high_reliability(self) -> None:
        # v8: 需要 31 个字段才能达到高覆盖率阈值
        fields = [
            InvoiceField(
                key=f"field_{i}",
                label=f"字段{i}",
                value=f"val{i}",
                confidence=0.95,
                desensitized=f"val{i}",
            )
            for i in range(31)
        ]
        groups = [FieldGroup(name="测试", fields=fields)]
        settings = Settings()
        result = evaluate_reliability(groups, settings)
        assert result.level == "high"

    def test_low_reliability_missing_fields(self) -> None:
        groups = [FieldGroup(name="基础信息", fields=[])]
        settings = Settings()
        result = evaluate_reliability(groups, settings)
        assert result.level == "low"
        assert "字段不完整" in result.reasons

    def test_low_reliability_low_confidence(self) -> None:
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


class TestIsValidValue:
    """v5: 值验证——拒绝标注性文本、其他关键词、身份证号。"""

    def test_annotation_daxie(self) -> None:
        assert not _is_valid_value("（大写)", None)

    def test_annotation_xiaoxie(self) -> None:
        assert not _is_valid_value("（小写)", None)

    def test_annotation_zhengshoulu(self) -> None:
        assert not _is_valid_value("/征收率", None)

    def test_annotation_nashui(self) -> None:
        assert not _is_valid_value("纳税人识别号", None)

    def test_valid_number_with_pattern(self) -> None:
        assert _is_valid_value("1234.56", r"[\d,]+\.?\d*")
        assert not _is_valid_value("（大写)", r"[\d,]+\.?\d*")

    def test_valid_percentage(self) -> None:
        assert _is_valid_value("6%", r"\d+%")
        assert not _is_valid_value("/征收率", r"\d+%")

    def test_valid_number_no_pattern(self) -> None:
        assert _is_valid_value("北京某公司", None)
        assert not _is_valid_value("（大写)", None)

    def test_reject_other_field_keyword(self) -> None:
        """v5: 值包含其他字段关键词时应拒绝。"""
        # "发票号码：26437000000160901743" 不应作为发票代码的值
        assert not _is_valid_value(
            "发票号码：26437000000160901743",
            r"\d{10,12}",
            current_field_key="invoice_code",
        )
        # 同上，不应作为校验码值
        assert not _is_valid_value(
            "发票号码：26437000000160901743",
            r"\d{16,20}",
            current_field_key="check_code",
        )

    def test_reject_id_number_pattern(self) -> None:
        """v5: 姓名+身份证号不应作为金额或税号。"""
        assert not _is_valid_value("董伟涛 430424199603275411", r"[¥￥]?[\d,]+\.?\d*")
        assert not _is_valid_value(
            "董伟涛 430424199603275411",
            r"[A-Za-z0-9]{15,20}",
            current_field_key="seller_tax_number",
        )

    def test_accept_same_field_keyword_in_value(self) -> None:
        """v5: 当前字段自己的关键词出现在值中不排斥。"""
        # "购方纳税人识别号91430100MA4LGPXRXR" 作为 buyer_tax_number 的值——关键词是自己的
        assert _is_valid_value(
            "91430100MA4LGPXRXR",
            r"[A-Za-z0-9]{15,20}",
            current_field_key="buyer_tax_number",
        )


class TestCleanValueV4:
    """v4: 值清洗增强——修复 OCR 空格噪声。"""

    def test_ocr_space_in_decimal(self) -> None:
        """OCR 空格噪声："1. 15" → "1.15"。"""
        assert _clean_value("1. 15") == "1.15"

    def test_ocr_space_before_decimal(self) -> None:
        """OCR 空格噪声："38 .49" → "38.49"。"""
        assert _clean_value("38 .49") == "38.49"

    def test_ocr_space_in_comma(self) -> None:
        """OCR 空格噪声："1, 234.56" → "1,234.56"。"""
        assert _clean_value("1, 234.56") == "1,234.56"


class TestInvoiceTemplateV4:
    """v4: 真实 OCR 数据驱动的修复测试。"""

    def test_reject_annotation_as_amount(self) -> None:
        """v4: "合计（大写）" 不应提取 "（大写)" 作为金额值。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 650, 200, 670), "价税合计（大写）壹佰叁拾玖元陆角肆分", 0.95),
            ((210, 650, 350, 670), "¥139.64", 0.90),
        ]
        groups = _call_map(template, ocr_results)
        amount_group = groups[1]
        # 如果找到 amount_with_tax，值应该是数字而非标注
        if any(f.key == "amount_with_tax" for f in amount_group.fields):
            amt = next(f for f in amount_group.fields if f.key == "amount_with_tax")
            assert amt.value != "（大写)", "v4 应拒绝标注性文本作为值"

    def test_reject_label_as_tax_rate(self) -> None:
        """v4: "/征收率" 不应作为税率值。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 650, 100, 670), "税率/征收率", 0.95),
            ((110, 650, 200, 670), "3%", 0.90),
        ]
        groups = _call_map(template, ocr_results)
        amount_group = groups[1]
        if any(f.key == "tax_rate" for f in amount_group.fields):
            tr = next(f for f in amount_group.fields if f.key == "tax_rate")
            assert "/征收率" not in tr.value, "v4 应拒绝标签性文本"

    def test_no_ambiguous_keyword_code(self) -> None:
        """v4: "代码" 不再作为发票代码关键词。"""
        assert "代码" not in FIELD_DEFINITIONS["invoice_code"]["keywords"]

    def test_no_ambiguous_keyword_number(self) -> None:
        """v4: "号码" 不再作为发票号码关键词。"""
        assert "号码" not in FIELD_DEFINITIONS["invoice_number"]["keywords"]

    def test_no_ambiguous_keyword_heji(self) -> None:
        """v4: "合计" 不再作为价税合计关键词。"""
        keywords = FIELD_DEFINITIONS["amount_with_tax"]["keywords"]
        assert "合计" not in keywords
        assert "合　计" not in keywords

    def test_invoice_number_has_kaiPiao_keyword(self) -> None:
        """v7: "开票号码" 作为发票号码关键词变体（全电发票）。"""
        assert "开票号码" in FIELD_DEFINITIONS["invoice_number"]["keywords"]

    def test_invoice_number_no_ambiguous_haoma(self) -> None:
        """v7: "号码" 不再作为发票号码关键词。"""
        assert "号码" not in FIELD_DEFINITIONS["invoice_number"]["keywords"]

    def test_new_fields_exist(self) -> None:
        """v7: 新增字段存在——发票类型、合计金额大写、价税合计大写。"""
        assert "invoice_type" in FIELD_DEFINITIONS
        assert "amount_without_tax_upper" in FIELD_DEFINITIONS
        assert "amount_with_tax_upper" in FIELD_DEFINITIONS
        assert FIELD_DEFINITIONS["invoice_type"]["group"] == "基础信息"
        assert FIELD_DEFINITIONS["amount_without_tax_upper"]["group"] == "金额信息"
        assert FIELD_DEFINITIONS["amount_with_tax_upper"]["group"] == "金额信息"

    def test_invoice_type_keywords(self) -> None:
        """v7: 发票类型关键词包含常见类型。"""
        kw = FIELD_DEFINITIONS["invoice_type"]["keywords"]
        assert "增值税普通发票" in kw
        assert "增值税专用发票" in kw


class TestCleanValueV7:
    """v7: 值清洗——移除标注性前缀（小写/大写）。"""

    def test_xiaoxie_prefix_strip(self) -> None:
        """v7: "（小写）¥139.64" → "139.64"。"""
        assert _clean_value("（小写）¥139.64") == "139.64"

    def test_daxie_prefix_strip(self) -> None:
        """v7: "（大写）壹佰叁拾玖元陆角肆分" → "壹佰叁拾玖元陆角肆分"。"""
        assert _clean_value("（大写）壹佰叁拾玖元陆角肆分") == "壹佰叁拾玖元陆角肆分"

    def test_xiaoxie_prefix_with_paren_strip(self) -> None:
        """v7: "(小写)¥139.64" → "139.64"（半角括号）。"""
        assert _clean_value("(小写)¥139.64") == "139.64"


class TestInvoiceTemplateV7:
    """v7: 开票号码关键词、标注前缀修复、新字段。"""

    def test_invoice_number_with_kaiPiao_keyword(self) -> None:
        """v7: "开票号码" 关键词变体提取。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 200, 150, 220), "开票号码", 0.98),
            ((160, 200, 250, 220), "12345678", 0.95),
        ]
        groups = _call_map(template, ocr_results)
        basic_group = groups[0]
        found = any(f.key == "invoice_number" for f in basic_group.fields)
        assert found, "v7 应能通过'开票号码'关键词提取发票号码"
        inv_num = next(f for f in basic_group.fields if f.key == "invoice_number")
        assert inv_num.value == "12345678"

    def test_amount_with_xiaoxie_prefix(self) -> None:
        """v7: 价税合计 OCR 输出包含"（小写）"前缀——应提取实际数值。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 650, 200, 670), "价税合计（大写）壹佰叁拾玖元陆角肆分", 0.95),
            ((210, 650, 350, 670), "（小写）¥139.64", 0.90),
        ]
        groups = _call_map(template, ocr_results)
        amount_group = groups[1]
        if any(f.key == "amount_with_tax" for f in amount_group.fields):
            amt = next(f for f in amount_group.fields if f.key == "amount_with_tax")
            assert amt.value == "139.64", "v7 应移除（小写）前缀后提取数值"

    def test_invoice_type_extraction(self) -> None:
        """v7: 发票类型提取。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((100, 50, 300, 70), "增值税普通发票", 0.97),
        ]
        groups = _call_map(template, ocr_results)
        basic_group = groups[0]
        found = any(f.key == "invoice_type" for f in basic_group.fields)
        assert found, "v7 应能提取发票类型"

    def test_amount_upper_extraction(self) -> None:
        """v7: 价税合计大写金额提取。"""
        template = InvoiceTemplate()
        ocr_results = [
            ((30, 650, 200, 670), "价税合计（大写）壹佰叁拾玖元陆角肆分", 0.95),
            ((210, 650, 350, 670), "（小写）¥139.64", 0.90),
        ]
        groups = _call_map(template, ocr_results)
        amount_group = groups[1]
        if any(f.key == "amount_with_tax_upper" for f in amount_group.fields):
            amt_upper = next(
                f for f in amount_group.fields if f.key == "amount_with_tax_upper"
            )
            # 大写金额应该包含中文数字字符
            assert "壹" in amt_upper.value or "玖" in amt_upper.value


class TestIsValidValueV8:
    """v8: full_match 模式——纯数字pattern必须全值匹配。"""

    def test_full_match_rejects_tax_number_as_machine_number(self) -> None:
        """v8: "91430100MA4LGPXRXR" 不应被 \\d{6,12} 子串匹配为机器编号。"""
        assert not _is_valid_value(
            "91430100MA4LGPXRXR",
            r"\d{6,12}",
            current_field_key="machine_number",
            full_match=True,
        )

    def test_full_match_accepts_pure_digit_value(self) -> None:
        """v8: "12345678" 纯8位数字应被 \\d{8,20} 全值匹配为发票号码。"""
        assert _is_valid_value(
            "12345678",
            r"\d{8,20}",
            current_field_key="invoice_number",
            full_match=True,
        )

    def test_full_match_rejects_mixed_value(self) -> None:
        """v8: "发票号码12345678" 不应被 \\d{8,20} 全值匹配。"""
        assert not _is_valid_value(
            "发票号码12345678",
            r"\d{8,20}",
            full_match=True,
        )

    def test_non_full_match_still_uses_search(self) -> None:
        """v8: 非 full_match 模式仍然使用 search（子串匹配）。"""
        # 金额pattern "1,234.56" 在 "¥1,234.56元" 中应找到子串
        assert _is_valid_value(
            "1,234.56",
            r"[\d,]+\.?\d*",
            full_match=False,
        )

    def test_full_match_accepts_tax_number(self) -> None:
        """v8: "91430100MA4LGPXRXR" 应被 [A-Za-z0-9]{15,20} 全值匹配为税号。"""
        assert _is_valid_value(
            "91430100MA4LGPXRXR",
            r"[A-Za-z0-9]{15,20}",
            current_field_key="buyer_tax_number",
            full_match=True,
        )

    def test_full_match_rejects_short_tax_number(self) -> None:
        """v8: "ABC" (3位) 不应被 [A-Za-z0-9]{15,20} 全值匹配。"""
        assert not _is_valid_value(
            "ABC",
            r"[A-Za-z0-9]{15,20}",
            full_match=True,
        )


class TestFieldDefinitionsV8:
    """v8: 关键词清理和出行字段验证。"""

    def test_no_ambiguous_keyword_name(self) -> None:
        """v8: "名称" 不再作为购方/销方名称关键词。"""
        assert "名称" not in FIELD_DEFINITIONS["buyer_name"]["keywords"]
        assert "名称" not in FIELD_DEFINITIONS["seller_name"]["keywords"]

    def test_no_ambiguous_keyword_jine(self) -> None:
        """v8: "金额" 不再作为不含税金额关键词。"""
        assert "金额" not in FIELD_DEFINITIONS["amount_without_tax"]["keywords"]

    def test_no_ambiguous_keyword_buyer(self) -> None:
        """v8: "购方" 不再作为购方名称关键词。"""
        assert "购方" not in FIELD_DEFINITIONS["buyer_name"]["keywords"]

    def test_no_ambiguous_keyword_seller(self) -> None:
        """v8: "销方" 不再作为销方名称关键词。"""
        assert "销方" not in FIELD_DEFINITIONS["seller_name"]["keywords"]

    def test_travel_fields_exist(self) -> None:
        """v8: 出行信息字段存在。"""
        assert "traveler_name" in FIELD_DEFINITIONS
        assert "traveler_id_number" in FIELD_DEFINITIONS
        assert "travel_date" in FIELD_DEFINITIONS
        assert "departure_place" in FIELD_DEFINITIONS
        assert "arrival_place" in FIELD_DEFINITIONS
        assert "travel_class" in FIELD_DEFINITIONS
        assert "transport_type" in FIELD_DEFINITIONS

    def test_travel_fields_group(self) -> None:
        """v8: 出行信息字段分组正确。"""
        for key in ["traveler_name", "traveler_id_number", "travel_date",
                     "departure_place", "arrival_place", "travel_class",
                     "transport_type"]:
            assert FIELD_DEFINITIONS[key]["group"] == "出行信息"

    def test_full_match_set_for_numeric_fields(self) -> None:
        """v8: 纯数字pattern字段设置了full_match=True。"""
        for key in ["invoice_code", "invoice_number", "invoice_date",
                     "check_code", "machine_number", "tax_rate",
                     "amount_without_tax_upper", "amount_with_tax_upper",
                     "buyer_tax_number", "seller_tax_number",
                     "traveler_id_number", "travel_date"]:
            assert FIELD_DEFINITIONS[key].get("full_match") is True
