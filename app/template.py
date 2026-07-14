"""票析 — 增值税发票模板

定义发票字段、版式区域划分和 KV 映射规则。
模板采用区域定位 + 关键词匹配双策略：
1. 区域定位——通过 OCR 文字框的 y 坐标归入对应版式区域
2. 关键词匹配——在区域内寻找特征关键词，将同一行中
   关键词右侧最近邻的文字框作为字段值

发票的版式特点：关键词在左，值在右，同一行排列。
PaddleOCR 可能将 "关键词+值" 识别为一个整体框，
也可能分成两个框。模板需要同时处理这两种情况。"""

from __future__ import annotations

# ── 字段定义 ──────────────────────────────────────────────────
# 每个字段包含：key（机器名）、label（中文显示名）、
# keywords（特征关键词列表，用于在 OCR 文本中定位）
# value_pattern（值的正则特征，用于区分关键词和值文字框）
import re
from typing import Literal

from app.config import Settings
from app.desensitize import desensitize_field
from app.schemas import (
    FieldGroup,
    InvoiceField,
    Reliability,
    ReliabilityReason,
)

FIELD_DEFINITIONS: dict[str, dict] = {
    # ── 基础信息组 ────────────────────────────────────────────
    "invoice_code": {
        "label": "发票代码",
        "keywords": ["发票代码", "代码"],
        "value_pattern": r"^\d{10,12}$",  # 10-12 位纯数字
        "group": "基础信息",
    },
    "invoice_number": {
        "label": "发票号码",
        "keywords": ["发票号码", "号码", "No"],
        "value_pattern": r"^\d{8}$",  # 8 位纯数字
        "group": "基础信息",
    },
    "invoice_date": {
        "label": "开票日期",
        "keywords": ["开票日期", "日期"],
        "value_pattern": r"\d{4}年\d{1,2}月\d{1,2}日",  # 日期格式
        "group": "基础信息",
    },
    "check_code": {
        "label": "校验码",
        "keywords": ["校验码"],
        "value_pattern": r"^\d{16,20}$",  # 16-20 位纯数字
        "group": "基础信息",
    },
    # ── 金额信息组 ────────────────────────────────────────────
    "amount_without_tax": {
        "label": "不含税金额",
        "keywords": ["不含税金额", "金额"],
        "value_pattern": r"^\d+\.?\d*$",  # 数字金额
        "group": "金额信息",
    },
    "tax_rate": {
        "label": "税率",
        "keywords": ["税率"],
        "value_pattern": r"^\d+%$",  # 百分比
        "group": "金额信息",
    },
    "tax_amount": {
        "label": "税额",
        "keywords": ["税额"],
        "value_pattern": r"^\d+\.?\d*$",  # 数字金额
        "group": "金额信息",
    },
    "amount_with_tax": {
        "label": "价税合计",
        "keywords": ["价税合计", "合计（大写）", "合 计"],
        "value_pattern": r"^¥?\d+\.?\d*$",  # ¥开头或纯数字金额
        "group": "金额信息",
    },
    # ── 购方信息组 ────────────────────────────────────────────
    "buyer_name": {
        "label": "购方名称",
        "keywords": ["购方名称", "购买方", "名称"],
        "value_pattern": None,  # 公司名称没有固定格式
        "group": "购方信息",
    },
    "buyer_tax_number": {
        "label": "购方纳税人识别号",
        "keywords": ["购方纳税人识别号", "购方识别号", "纳税人识别号"],
        "value_pattern": r"^[A-Z0-9]{15,20}$",  # 税号格式
        "group": "购方信息",
    },
    "buyer_address_phone": {
        "label": "购方地址、电话",
        "keywords": ["购方地址", "地址电话", "地址、电话"],
        "value_pattern": None,
        "group": "购方信息",
    },
    "buyer_bank_account": {
        "label": "购方开户行及账号",
        "keywords": ["购方开户行", "开户行及账号", "开户行"],
        "value_pattern": None,
        "group": "购方信息",
    },
    # ── 销方信息组 ────────────────────────────────────────────
    "seller_name": {
        "label": "销方名称",
        "keywords": ["销方名称", "销售方", "名称"],
        "value_pattern": None,
        "group": "销方信息",
    },
    "seller_tax_number": {
        "label": "销方纳税人识别号",
        "keywords": ["销方纳税人识别号", "销方识别号"],
        "value_pattern": r"^[A-Z0-9]{15,20}$",
        "group": "销方信息",
    },
    "seller_address_phone": {
        "label": "销方地址、电话",
        "keywords": ["销方地址"],
        "value_pattern": None,
        "group": "销方信息",
    },
    "seller_bank_account": {
        "label": "销方开户行及账号",
        "keywords": ["销方开户行"],
        "value_pattern": None,
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


def _is_on_same_line(
    box1: tuple[float, float, float, float],
    box2: tuple[float, float, float, float],
    tolerance: float = 15.0,
) -> bool:
    """判断两个文字框是否在同一行——y 坐标中心差距小于 tolerance。"""
    center_y1 = (box1[1] + box1[3]) / 2
    center_y2 = (box2[1] + box2[3]) / 2
    return abs(center_y1 - center_y2) < tolerance


def _find_value_near_keyword(
    keyword_idx: int,
    annotated: list[tuple],
    value_pattern: str | None,
) -> tuple[str, float]:
    """在关键词右侧同一行中查找字段值。

    搜索策略：
    1. 先在同区域、同一行的文字框中，找关键词右侧最近邻的框
    2. 如果有 value_pattern 正则，优先匹配符合格式的文字框
    3. 如果没有 value_pattern，取右侧最近邻的文字框（排除本身是关键词的框）

    返回 (value, confidence)。如果找不到，返回 ("", 0.0)。
    """
    _, keyword_text, keyword_conf, keyword_box = annotated[keyword_idx]
    (keyword_box[1] + keyword_box[3]) / 2
    keyword_right_x = keyword_box[2]  # 关键词框的右边界

    candidates: list[tuple[float, str, float, tuple]] = []  # (distance, text, conf, box)

    for j, (_region, text, conf, box) in enumerate(annotated):
        if j == keyword_idx:
            continue

        # ── 必须在同一行 ────────────────────────────────────────
        if not _is_on_same_line(keyword_box, box):
            continue

        # ── 必须在关键词右侧 ────────────────────────────────────
        candidate_left_x = box[0]
        if candidate_left_x < keyword_right_x - 5:  # 允许 5px 容差
            continue

        # ── 计算水平距离 ────────────────────────────────────────
        distance = candidate_left_x - keyword_right_x
        candidates.append((distance, text, conf, box))

    if not candidates:
        return "", 0.0

    # ── 优先匹配 value_pattern ────────────────────────────────────
    if value_pattern:
        pattern_matched = [
            (dist, text, conf, box)
            for dist, text, conf, box in candidates
            if re.search(value_pattern, text)
        ]
        if pattern_matched:
            # 取距离最近的匹配框
            pattern_matched.sort(key=lambda x: x[0])
            return pattern_matched[0][1], pattern_matched[0][2]

    # ── 无 value_pattern 或未匹配——取最近邻 ──────────────────────
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2]


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
            center_y = (box[1] + box[3]) / 2
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

            value_pattern = field_def.get("value_pattern")
            best_match: tuple[str, float] = ("", 0.0)

            # ── 策略 A: 关键词单独识别——找关键词框右侧同行的值 ────
            for i, (region, text, _conf, _box) in enumerate(annotated):
                # 关键词必须在对应区域
                if expected_region and region != expected_region:
                    continue

                for keyword in field_def["keywords"]:
                    # 关键词完全匹配或包含匹配
                    if keyword in text:
                        # 如果关键词文本本身就是完整内容（如 "发票号码12345678"），
                        # 尝试从文本中提取值
                        value_in_text = self._extract_value_from_text(text, keyword, value_pattern)
                        if value_in_text:
                            best_match = (value_in_text, annotated[i][2])
                            break

                        # 关键词单独识别，在右侧同行查找值
                        value, value_conf = _find_value_near_keyword(i, annotated, value_pattern)
                        if value and value_conf > best_match[1]:
                            best_match = (value, value_conf)
                        break  # 找到一个关键词匹配即可

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

    def _extract_value_from_text(
        self,
        text: str,
        keyword: str,
        value_pattern: str | None,
    ) -> str | None:
        """从关键词+值合并识别的文本中提取值。

        例如 PaddleOCR 可能识别出 "发票号码12345678" 这样的整体文本，
        此时需要从文本中分离出关键词和值。
        """
        # 移除关键词部分，留下剩余文本
        remaining = text.replace(keyword, "").strip()

        # 移除常见分隔符（冒号、空格等）
        remaining = remaining.lstrip(":：").strip()

        if not remaining:
            return None

        # 如果有 value_pattern，检查剩余文本是否匹配
        if value_pattern:
            if re.search(value_pattern, remaining):
                return remaining
            # 即使不匹配正则，如果剩余文本看起来像值（不是另一个关键词），也返回
            if remaining and len(remaining) >= 2:
                return remaining

        # 无 value_pattern——只要剩余文本存在且不像关键词，就返回
        if remaining and len(remaining) >= 2:
            return remaining

        return None


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
