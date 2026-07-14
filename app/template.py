"""票析 — 增值税发票模板

定义发票字段、版式区域划分和 KV 映射规则。
模板采用区域定位 + 关键词匹配双策略：
1. 区域定位——通过 OCR 文字框的 y 坐标归入对应版式区域
2. 关键词匹配——在区域内寻找特征关键词，将关键词附近的文字框作为字段值"""

from __future__ import annotations

from typing import Literal

from app.config import Settings
from app.desensitize import desensitize_field
from app.schemas import (
    FieldGroup,
    InvoiceField,
    Reliability,
    ReliabilityReason,
)

# ── 字段定义 ──────────────────────────────────────────────────
# 每个字段包含：key（机器名）、label（中文显示名）、
# keywords（特征关键词列表，用于在 OCR 文本中定位）

FIELD_DEFINITIONS: dict[str, dict] = {
    # ── 基础信息组 ────────────────────────────────────────────
    "invoice_code": {
        "label": "发票代码",
        "keywords": ["发票代码", "代码"],
        "group": "基础信息",
    },
    "invoice_number": {
        "label": "发票号码",
        "keywords": ["发票号码", "号码", "No"],
        "group": "基础信息",
    },
    "invoice_date": {
        "label": "开票日期",
        "keywords": ["开票日期", "日期"],
        "group": "基础信息",
    },
    "check_code": {
        "label": "校验码",
        "keywords": ["校验码"],
        "group": "基础信息",
    },
    # ── 金额信息组 ────────────────────────────────────────────
    "amount_without_tax": {
        "label": "不含税金额",
        "keywords": ["合计", "金额", "不含税"],
        "group": "金额信息",
    },
    "tax_rate": {
        "label": "税率",
        "keywords": ["税率"],
        "group": "金额信息",
    },
    "tax_amount": {
        "label": "税额",
        "keywords": ["税额"],
        "group": "金额信息",
    },
    "amount_with_tax": {
        "label": "价税合计",
        "keywords": ["价税合计", "合计"],
        "group": "金额信息",
    },
    # ── 购方信息组 ────────────────────────────────────────────
    "buyer_name": {
        "label": "购方名称",
        "keywords": ["购方名称", "购买方", "名称"],
        "group": "购方信息",
    },
    "buyer_tax_number": {
        "label": "购方纳税人识别号",
        "keywords": ["购方纳税人识别号", "购方识别号", "纳税人识别号"],
        "group": "购方信息",
    },
    "buyer_address_phone": {
        "label": "购方地址、电话",
        "keywords": ["购方地址", "地址电话", "地址、电话"],
        "group": "购方信息",
    },
    "buyer_bank_account": {
        "label": "购方开户行及账号",
        "keywords": ["购方开户行", "开户行及账号", "开户行"],
        "group": "购方信息",
    },
    # ── 销方信息组 ────────────────────────────────────────────
    "seller_name": {
        "label": "销方名称",
        "keywords": ["销方名称", "销售方", "名称"],
        "group": "销方信息",
    },
    "seller_tax_number": {
        "label": "销方纳税人识别号",
        "keywords": ["销方纳税人识别号", "销方识别号"],
        "group": "销方信息",
    },
    "seller_address_phone": {
        "label": "销方地址、电话",
        "keywords": ["销方地址"],
        "group": "销方信息",
    },
    "seller_bank_account": {
        "label": "销方开户行及账号",
        "keywords": ["销方开户行"],
        "group": "销方信息",
    },
}

# ── 区域定义 ──────────────────────────────────────────────────
# 按发票标准版式的 y 坐标百分比划分区域
# 坐标百分比 = OCR 文字框中心 y / 图片高度

REGIONS: dict[str, tuple[float, float]] = {
    "header": (0.00, 0.15),  # 顶部标题区
    "basic_info": (0.15, 0.28),  # 基础信息区（代码号码日期）
    "buyer_info": (0.28, 0.45),  # 购方信息区
    "item_detail": (0.45, 0.62),  # 明细项目区（不提取）
    "amount_info": (0.62, 0.75),  # 金额信息区
    "seller_info": (0.75, 0.90),  # 销方信息区
    "footer": (0.90, 1.00),  # 底部备注区（不提取）
}

# ── 区域与字段组的对应关系 ────────────────────────────────────
REGION_GROUP_MAP: dict[str, str] = {
    "basic_info": "基础信息",
    "buyer_info": "购方信息",
    "amount_info": "金额信息",
    "seller_info": "销方信息",
}


def _classify_region(center_y: float, image_height: float) -> str:
    """根据 y 坐标百分比判断 OCR 文字框所属版式区域。"""
    ratio = center_y / image_height
    for region_name, (low, high) in REGIONS.items():
        if low <= ratio < high:
            return region_name
    return "unknown"


def _find_keyword_value(
    keyword_text_index: int,
    ocr_results: list[tuple],
    max_offset: int = 2,
) -> tuple[str, float]:
    """在关键词附近查找字段值——关键词后 max_offset 个文字框内选取。

    返回 (value, confidence)。如果附近没有合适的值，返回 ("", 0.0)。
    """
    for offset in range(1, max_offset + 1):
        idx = keyword_text_index + offset
        if idx >= len(ocr_results):
            break
        _, text, confidence = ocr_results[idx]
        return text, confidence
    return "", 0.0


class InvoiceTemplate:
    """增值税发票模板——将 OCR 识别结果映射为结构化字段。"""

    def map_results(
        self,
        ocr_results: list[tuple],
        image_height: float,
    ) -> list[FieldGroup]:
        """将 PaddleOCR 识别结果映射为字段分组。

        参数：
            ocr_results: PaddleOCR 输出列表，每项为 ((x1,y1,x2,y2), text, confidence)
            image_height: 图片像素高度，用于区域定位

        返回：按组分类的 InvoiceField 列表。
        """
        # ── Step 1: 为每个 OCR 文字框标记所属区域 ────────────
        annotated: list[tuple[str, str, float, tuple]] = []
        for box, text, conf in ocr_results:
            # 计算文字框中心 y 坐标
            y1, y3 = box[1], box[3]
            center_y = (y1 + y3) / 2
            region = _classify_region(center_y, image_height)
            annotated.append((region, text, conf, box))

        # ── Step 2: 按关键词匹配提取字段值 ────────────────────
        extracted: dict[str, InvoiceField] = {}

        for field_key, field_def in FIELD_DEFINITIONS.items():
            expected_group = field_def["group"]
            expected_region = None
            for reg_name, grp_name in REGION_GROUP_MAP.items():
                if grp_name == expected_group:
                    expected_region = reg_name

            # 在所有 OCR 文字中寻找关键词
            best_match: tuple[str, float] = ("", 0.0)

            for i, (region, text, conf, _) in enumerate(annotated):
                # 关键词必须在对应区域
                if expected_region and region != expected_region:
                    continue

                for keyword in field_def["keywords"]:
                    if keyword in text:
                        value, value_conf = _find_keyword_value(i, ocr_results)
                        if value and value_conf > best_match[1]:
                            best_match = (value, value_conf)

            if best_match[0]:
                desensitized = desensitize_field(field_key, best_match[0])
                extracted[field_key] = InvoiceField(
                    key=field_key,
                    label=field_def["label"],
                    value=best_match[0],
                    confidence=best_match[1],
                    desensitized=desensitized,
                )

        # ── Step 3: 按组聚合 ────────────────────────────────────
        group_names = ["基础信息", "金额信息", "购方信息", "销方信息"]
        groups: list[FieldGroup] = []
        for group_name in group_names:
            fields = [
                extracted[k]
                for k, d in FIELD_DEFINITIONS.items()
                if d["group"] == group_name and k in extracted
            ]
            groups.append(FieldGroup(name=group_name, fields=fields))

        return groups


def evaluate_reliability(
    groups: list[FieldGroup],
    settings: Settings,
) -> Reliability:
    """评估识别结果的可靠性——诚实降级机制。

    三项检查：
    1. 关键字段缺失率 > threshold → "字段不完整"
    2. 平均置信度 < threshold → "识别置信度偏低"
    3. 字段覆盖率 < threshold → "模板匹配不足"

    任一触发 → level = "low"，否则 "high"。
    """
    total_defined = len(FIELD_DEFINITIONS)
    total_extracted = sum(len(g.fields) for g in groups)

    reasons: list[ReliabilityReason] = []

    # ── 检查 1: 字段缺失率 ────────────────────────────────────
    missing_ratio = 1 - (total_extracted / total_defined)
    if missing_ratio > settings.field_missing_ratio_threshold:
        reasons.append("字段不完整")

    # ── 检查 2: 平均置信度 ────────────────────────────────────
    if total_extracted > 0:
        avg_conf = sum(f.confidence for g in groups for f in g.fields) / total_extracted
        if avg_conf < settings.avg_confidence_threshold:
            reasons.append("识别置信度偏低")

    # ── 检查 3: 字段覆盖率 ────────────────────────────────────
    coverage = total_extracted / total_defined
    if coverage < settings.field_coverage_threshold:
        reasons.append("模板匹配不足")

    level: Literal["high", "low"] = "low" if reasons else "high"
    return Reliability(level=level, reasons=reasons)
