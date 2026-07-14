"""票析 — 增值税发票模板

v4 修复——基于真实 OCR 数据的精准修复：

真实发票 OCR 输出暴露了 3 个核心问题：
1. 关键词太短太贪心——"代码"匹配到了无关文本，"合计"匹配了"合计（大写）"
2. 值验证太弱——"（大写)"、"/征收率" 这些标注文本被当作值接受
3. 合并文本提取不够智能——关键词剩余部分可能是标注而非值

v4 修复策略：
- 删除歧义短关键词（"代码"、"号码"、"日期"）
- 新增 _is_valid_value() 严格验证——拒绝标注性文本、其他标签、纯括号内容
- value_pattern 有定义的字段：必须匹配才接受，不接受 pattern 不匹配的兜底值
- _clean_value 增强——移除 OCR 常见的空格噪声（如 "1. 15" → "1.15")
- 合并文本提取：标注性后缀（（大写)、（小写)、/征收率）直接跳过"""

from __future__ import annotations

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

# ── 值验证：拒绝标注性文本 ────────────────────────────────────
ANNOTATION_PATTERNS = [
    r"^[\(（][大小]写[\)）]",  # （大写)、（小写)
    r"^[/／]征收率",  # /征收率
    r"^纳税人识别号",  # 纳税人识别号
    r"^[\(（]\s*[\)）]$",  # 空括号
]


def _is_valid_value(
    value: str,
    value_pattern: str | None,
    current_field_key: str | None = None,
    full_match: bool = False,
) -> bool:
    """验证提取的值是否合法。

    v5 新增规则：
    1. 拒绝标注性文本（（大写)、/征收率 等）
    2. 有 value_pattern 时必须匹配
    3. v5: 拒绝包含其他字段关键词的值（如 "发票号码：xxx" 不应作为发票代码值）
    4. v5: 拒绝明显不是正确类型的值（如姓名+身份证号不应作为金额）

    v8 新增规则：
    5. full_match 模式——纯数字/纯字母数字pattern必须匹配整个值，
       防止子串误匹配（如 "91430100MA4LGPXRXR" 中的 "91430100"
       被 \\d{6,12} 子串匹配为机器编号）
    """
    if not value or len(value.strip()) < 1:
        return False

    # 规则 1: 拒绝标注性文本
    for pattern in ANNOTATION_PATTERNS:
        if re.search(pattern, value):
            return False

    # 规则 2: 有 value_pattern 时必须匹配
    if value_pattern:
        if full_match:
            # v8: full_match 模式——pattern 必须匹配整个值
            # 防止 "91430100MA4LGPXRXR" 被 \\d{6,12} 子串匹配
            if not re.fullmatch(value_pattern, value):
                return False
        else:
            # 普通模式——pattern 只需在值中找到匹配即可
            if not re.search(value_pattern, value):
                return False

    # 规则 3: v5 — 拒绝包含其他字段关键词的值
    # "发票号码：26437000000160901743" 含有 "发票号码"，不应作为其他字段值
    if current_field_key:
        current_keywords = set(FIELD_DEFINITIONS[current_field_key]["keywords"])
        for kw in ALL_FIELD_KEYWORDS_SET:
            if kw in current_keywords:
                continue  # 当前字段自己的关键词不排斥
            if kw in value:
                return False

    # 规则 4: v5 — 拒绝明显不是正确类型的值
    # 身份证号模式（姓名 + 18位数字）不应作为金额或税号
    return not re.search(r"[一-鿿]{2,4}\s*\d{17}[\dXx]", value)


# ── 字段定义 ──────────────────────────────────────────────────
# v4: 删除歧义短关键词（"代码"、"号码"、"日期"），
# v8: 继续删除歧义短关键词（"名称"、"金额"、"购方"、"销方"、"开户行"、"地址电话"）
# 只保留完整、明确的关键词
FIELD_DEFINITIONS: dict[str, dict] = {
    # ── 基础信息组 ────────────────────────────────────────────
    "invoice_code": {
        "label": "发票代码",
        "keywords": ["发票代码"],
        "value_pattern": r"\d{10,12}",
        "full_match": True,  # v8: 纯数字pattern必须全值匹配
        "group": "基础信息",
        "search_mode": "right",
    },
    "invoice_number": {
        "label": "发票号码",
        "keywords": ["发票号码", "开票号码"],
        "value_pattern": r"\d{8,20}",
        "full_match": True,  # v8: 纯数字pattern必须全值匹配
        "group": "基础信息",
        "search_mode": "right",
    },
    "invoice_date": {
        "label": "开票日期",
        "keywords": ["开票日期"],
        "value_pattern": r"\d{4}年\d{1,2}月\d{1,2}日",
        "full_match": True,  # v8: 日期格式必须全值匹配
        "group": "基础信息",
        "search_mode": "right",
    },
    "check_code": {
        "label": "校验码",
        "keywords": ["校验码"],
        "value_pattern": r"\d{16,20}",
        "full_match": True,  # v8: 纯数字pattern必须全值匹配
        "group": "基础信息",
        "search_mode": "right",
    },
    "machine_number": {
        "label": "机器编号",
        "keywords": ["机器编号"],
        "value_pattern": r"\d{6,12}",
        "full_match": True,  # v8: 纯数字pattern必须全值匹配，防止税号被子串匹配
        "group": "基础信息",
        "search_mode": "right",
    },
    "invoice_type": {
        "label": "发票类型",
        "keywords": [
            "增值税普通发票",
            "增值税专用发票",
            "增值税电子普通发票",
            "增值税电子专用发票",
            "全电发票",
        ],
        "value_pattern": None,
        "group": "基础信息",
        "search_mode": "nearby",
    },
    # ── 金额信息组 ────────────────────────────────────────────
    "amount_without_tax": {
        "label": "不含税金额",
        # v8: 移除"金额"——太贪心，会匹配"金额信息"、"合计金额（大写）"等
        "keywords": ["不含税金额", "合计金额", "合　计金额"],
        "value_pattern": r"[\d,]+\.?\d*",
        "group": "金额信息",
        "search_mode": "nearby",
    },
    "tax_rate": {
        "label": "税率",
        "keywords": ["税率"],
        "value_pattern": r"\d+%",
        "full_match": True,  # v8: 税率必须是完整百分比格式
        "group": "金额信息",
        "search_mode": "nearby",
    },
    "tax_amount": {
        "label": "税额",
        "keywords": ["税额"],
        "value_pattern": r"[\d,]+\.?\d*",
        "group": "金额信息",
        "search_mode": "nearby",
    },
    "amount_with_tax": {
        "label": "价税合计",
        "keywords": [
            "价税合计（小写）",
            "价税合计（大写）",
            "价税合计",
        ],
        "value_pattern": r"[¥￥]?[\d,]+\.?\d*",
        "group": "金额信息",
        "search_mode": "nearby",
    },
    "amount_without_tax_upper": {
        "label": "合计金额（大写）",
        "keywords": ["合计金额（大写）", "合计（大写）", "金额（大写）"],
        "value_pattern": r"[壹贰叁肆伍陆柒捌玖拾佰仟万亿零整元角分]+",
        "full_match": True,  # v8: 中文大写金额必须全值匹配
        "group": "金额信息",
        "search_mode": "nearby",
    },
    "amount_with_tax_upper": {
        "label": "价税合计（大写）",
        "keywords": ["价税合计（大写）"],
        "value_pattern": r"[壹贰叁肆伍陆柒捌玖拾佰仟万亿零整元角分]+",
        "full_match": True,  # v8: 中文大写金额必须全值匹配
        "group": "金额信息",
        "search_mode": "nearby",
    },
    # ── 购方信息组 ────────────────────────────────────────────
    "buyer_name": {
        "label": "购方名称",
        # v8: 移除"名称"、"购方"——太贪心，"名称"匹配"服务名称"等，
        #     "购方"匹配"购方信息"标题导致只提取到碎片
        "keywords": ["购买方名称", "购方名称", "买方名称", "购买方名称"],
        "value_pattern": None,
        "group": "购方信息",
        "search_mode": "nearby",
    },
    "buyer_tax_number": {
        "label": "购方纳税人识别号",
        # v8: 移除"纳税人识别号"——太贪心，会同时匹配购方和销方
        #     移除"统一社会信用代码"——同样会同时匹配购方和销方
        "keywords": [
            "购方纳税人识别号",
            "购方识别号",
            "购买方纳税人识别号",
            "买方纳税人识别号",
            "购买方识别号",
        ],
        "value_pattern": r"[A-Za-z0-9]{15,20}",
        "full_match": True,  # v8: 税号必须全值匹配
        "group": "购方信息",
        "search_mode": "nearby",
    },
    "buyer_address_phone": {
        "label": "购方地址、电话",
        # v8: 移除"地址电话"、"地址、电话"、"购方地址"——太贪心
        "keywords": [
            "购方地址、电话",
            "购买方地址、电话",
            "购方地址电话",
        ],
        "value_pattern": None,
        "group": "购方信息",
        "search_mode": "nearby",
    },
    "buyer_bank_account": {
        "label": "购方开户行及账号",
        # v8: 移除"开户行及账号"、"购方开户行"、"开户行"——太贪心
        "keywords": [
            "购方开户行及账号",
            "购买方开户行及账号",
            "购方开户行账号",
        ],
        "value_pattern": None,
        "group": "购方信息",
        "search_mode": "nearby",
    },
    # ── 销方信息组 ────────────────────────────────────────────
    "seller_name": {
        "label": "销方名称",
        # v8: 同购方，移除"名称"、"销方"
        "keywords": ["销售方名称", "销方名称", "卖方名称", "销售方名称"],
        "value_pattern": None,
        "group": "销方信息",
        "search_mode": "nearby",
    },
    "seller_tax_number": {
        "label": "销方纳税人识别号",
        # v8: 移除"纳税人识别号"、"统一社会信用代码"——太贪心
        "keywords": [
            "销方纳税人识别号",
            "销方识别号",
            "销售方纳税人识别号",
            "卖方纳税人识别号",
            "销售方识别号",
        ],
        "value_pattern": r"[A-Za-z0-9]{15,20}",
        "full_match": True,  # v8: 税号必须全值匹配
        "group": "销方信息",
        "search_mode": "nearby",
    },
    "seller_address_phone": {
        "label": "销方地址、电话",
        # v8: 移除"销方地址"——太贪心
        "keywords": [
            "销方地址、电话",
            "销售方地址、电话",
            "销方地址电话",
        ],
        "value_pattern": None,
        "group": "销方信息",
        "search_mode": "nearby",
    },
    "seller_bank_account": {
        "label": "销方开户行及账号",
        # v8: 移除"开户行"相关短关键词
        "keywords": [
            "销方开户行及账号",
            "销售方开户行及账号",
            "销方开户行账号",
        ],
        "value_pattern": None,
        "group": "销方信息",
        "search_mode": "nearby",
    },
    # ── 其他信息组 ────────────────────────────────────────────
    "issuer": {
        "label": "开票人",
        "keywords": ["开票人"],
        "value_pattern": None,
        "group": "其他信息",
        "search_mode": "nearby",
    },
    "payee": {
        "label": "收款人",
        "keywords": ["收款人"],
        "value_pattern": None,
        "group": "其他信息",
        "search_mode": "nearby",
    },
    "reviewer": {
        "label": "复核人",
        "keywords": ["复核人"],
        "value_pattern": None,
        "group": "其他信息",
        "search_mode": "nearby",
    },
    "remarks": {
        "label": "备注",
        "keywords": ["备注"],
        "value_pattern": None,
        "group": "其他信息",
        "search_mode": "nearby",
    },
    # ── 出行信息组（火车票/机票/通行费发票）─────────────────────
    "traveler_name": {
        "label": "出行人",
        "keywords": ["出行人", "乘车人", "旅客姓名", "姓名"],
        "value_pattern": None,
        "group": "出行信息",
        "search_mode": "nearby",
    },
    "traveler_id_number": {
        "label": "有效身份证件号",
        "keywords": ["有效身份证件号", "身份证号", "证件号码", "身份证件号"],
        "value_pattern": r"[A-Za-z0-9]{6,20}",
        "full_match": True,
        "group": "出行信息",
        "search_mode": "nearby",
    },
    "travel_date": {
        "label": "出行日期",
        "keywords": ["出行日期", "乘车日期", "出发时间", "航班日期"],
        "value_pattern": r"\d{4}年\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2}",
        "full_match": True,
        "group": "出行信息",
        "search_mode": "nearby",
    },
    "departure_place": {
        "label": "出发地",
        "keywords": ["出发地", "出发站", "始发地", "始发站"],
        "value_pattern": None,
        "group": "出行信息",
        "search_mode": "nearby",
    },
    "arrival_place": {
        "label": "到达地",
        "keywords": ["到达地", "到达站", "目的地", "终点站"],
        "value_pattern": None,
        "group": "出行信息",
        "search_mode": "nearby",
    },
    "travel_class": {
        "label": "等级",
        "keywords": ["等级", "席别", "座席等级", "舱位等级", "座位等级"],
        "value_pattern": None,
        "group": "出行信息",
        "search_mode": "nearby",
    },
    "transport_type": {
        "label": "交通工具类型",
        "keywords": ["交通工具类型", "交通类型", "车型", "车次", "航班号"],
        "value_pattern": None,
        "group": "出行信息",
        "search_mode": "nearby",
    },
}

# ── v5: 收集所有字段关键词 ──────────────────────────────────────
# 用于拒绝包含其他字段关键词的候选值
# 例如 "发票号码：26437000000160901743" 含 "发票号码"，不应作为发票代码值
ALL_FIELD_KEYWORDS_SET: set[str] = set()
for _fd in FIELD_DEFINITIONS.values():
    for _kw in _fd["keywords"]:
        ALL_FIELD_KEYWORDS_SET.add(_kw)

# ── 区域定义（宽松边界，带重叠容差）──────────────────────────
OVERLAP_MARGIN = 0.05

REGIONS: dict[str, tuple[float, float]] = {
    "header": (0.00, 0.15 + OVERLAP_MARGIN),
    "basic_info": (0.15 - OVERLAP_MARGIN, 0.28 + OVERLAP_MARGIN),
    "buyer_info": (0.28 - OVERLAP_MARGIN, 0.45 + OVERLAP_MARGIN),
    "item_detail": (0.45 - OVERLAP_MARGIN, 0.62 + OVERLAP_MARGIN),
    "amount_info": (0.62 - OVERLAP_MARGIN, 0.75 + OVERLAP_MARGIN),
    "seller_info": (0.75 - OVERLAP_MARGIN, 0.90 + OVERLAP_MARGIN),
    "footer": (0.90 - OVERLAP_MARGIN, 1.00),
}

REGION_GROUP_MAP: dict[str, str] = {
    "basic_info": "基础信息",
    "buyer_info": "购方信息",
    "amount_info": "金额信息",
    "seller_info": "销方信息",
    "item_detail": "出行信息",  # v8: 出行信息用 item_detail 区域（发票中部）
}

GROUP_REGION_MAP: dict[str, str] = {v: k for k, v in REGION_GROUP_MAP.items()}


def _classify_region(center_y: float, image_height: float) -> list[str]:
    """根据 y 坐标百分比判断 OCR 文字框所属版式区域——返回多区域匹配列表。"""
    ratio = center_y / image_height
    matched: list[tuple[float, str]] = []
    for region_name, (low, high) in REGIONS.items():
        if low <= ratio < high:
            center = (low + high) / 2
            dist = abs(ratio - center)
            half_width = (high - low) / 2
            score = 1.0 - (dist / half_width) if half_width > 0 else 1.0
            matched.append((score, region_name))
    matched.sort(key=lambda x: -x[0])
    return [name for _, name in matched]


def _clean_value(raw: str) -> str:
    """清洗提取的值——移除常见 OCR 噪声。

    v5 增强：
    - 移除标签前缀（如 "统一社会信用代码/纳税人识别号：" → 留纯值）
    - 移除 ¥/￥ 前缀、元后缀、冒号
    - 修复 OCR 空格噪声
    v7 增强：
    - 移除标注性前缀（如 "（小写）¥139.64" → "139.64"）
      注意：_is_valid_value 会拒绝纯标注文本（如 "（大写)" 本身），
      但标注前缀后面跟着实际值的情况应保留值部分
    """
    value = raw.strip()

    # v7: 移除标注性前缀——（小写）、（大写）后面跟着实际值的常见 OCR 输出
    # 如 "（小写）¥139.64" → 先移除 "（小写）" → "¥139.64" → 再移除 ¥ → "139.64"
    value = re.sub(r"^[\(（][大小]写[\)）]\s*", "", value)

    # v5: 移除常见标签前缀（如 "统一社会信用代码/纳税人识别号："）
    value = re.sub(r"^统一社会信用代码[/／]纳税人识别号[：:]\s*", "", value)
    # 移除 "纳税人识别号：" 前缀
    value = re.sub(r"^纳税人识别号[：:]\s*", "", value)
    # 移除通用 "XXX：" 标签前缀（中文标签+冒号+空格）
    value = re.sub(r"^[一-鿿]+[/／][一-鿿]+[：:]\s*", "", value)

    # 移除金额前缀
    value = re.sub(r"[¥￥]\s*", "", value)
    # 移除金额后缀
    value = re.sub(r"元\)?$", "", value)
    # 移除冒号
    value = value.lstrip("：").lstrip(":").strip()
    # 修复数字间的 OCR 空格噪声（如 "1. 15" → "1.15"）
    value = re.sub(r"(\d)\s*[.．]\s*(\d)", r"\1.\2", value)
    # 修复逗号间的空格（如 "1, 234" → "1,234"）
    value = re.sub(r"(\d)\s*,\s*(\d)", r"\1,\2", value)
    return value.strip()


def _spatial_distance(
    keyword_box: tuple[float, float, float, float],
    candidate_box: tuple[float, float, float, float],
) -> float:
    """计算两个框之间的空间距离。"""
    kw_center_x = (keyword_box[0] + keyword_box[2]) / 2
    kw_center_y = (keyword_box[1] + keyword_box[3]) / 2
    cand_center_x = (candidate_box[0] + candidate_box[2]) / 2
    cand_center_y = (candidate_box[1] + candidate_box[3]) / 2

    h_dist = cand_center_x - kw_center_x
    v_dist = abs(cand_center_y - kw_center_y)
    left_penalty = 100.0 if h_dist < -5 else 0.0

    return abs(h_dist) * 1.0 + v_dist * 0.3 + left_penalty


class InvoiceTemplate:
    """增值税发票模板——v4 精准修复版。"""

    def map_results(
        self,
        ocr_results: list[tuple],
        image_height: float,
        *,
        debug: bool = True,
    ) -> tuple[list[FieldGroup], list[dict]]:
        """将 PaddleOCR 识别结果映射为字段分组。

        v4 关键改进：所有候选值必须通过 _is_valid_value() 验证。
        """
        if not ocr_results:
            return self._empty_groups(), []

        trace: list[dict] = []

        # ── Step 1: 标记区域 ──────────────────────────────────────
        annotated: list[tuple[list[str], str, float, tuple]] = []
        ocr_raw_trace = []
        for idx, (box, text, conf) in enumerate(ocr_results):
            center_y = (box[1] + box[3]) / 2
            regions = _classify_region(center_y, image_height)
            annotated.append((regions, text, conf, box))
            ocr_raw_trace.append(
                {
                    "idx": idx,
                    "text": text,
                    "conf": round(conf, 3),
                    "box": [round(v, 1) for v in box],
                    "y_ratio": round(center_y / image_height, 3),
                    "regions": regions,
                }
            )
        if debug:
            trace.append({"step": "ocr_raw", "count": len(ocr_results), "boxes": ocr_raw_trace})

        # ── Step 2: 按关键词匹配提取字段值 ────────────────────
        # v4: 值必须通过 _is_valid_value() 验证才接受
        extracted: dict[str, InvoiceField] = {}

        for field_key, field_def in FIELD_DEFINITIONS.items():
            value_pattern = field_def.get("value_pattern")
            search_mode = field_def.get("search_mode", "right")
            expected_group = field_def["group"]
            expected_region = GROUP_REGION_MAP.get(expected_group)

            sorted_keywords = sorted(
                field_def["keywords"],
                key=lambda k: len(k),
                reverse=True,
            )

            field_trace: dict = {
                "field": field_key,
                "label": field_def["label"],
                "group": expected_group,
                "expected_region": expected_region,
                "keywords_tried": [],
                "result": "not_found",
            }

            best_match: tuple[str, float, str] = ("", 0.0, "")
            best_region_match: tuple[str, float, str] = ("", 0.0, "")

            for i, (regions, text, _conf, keyword_box) in enumerate(annotated):
                for keyword in sorted_keywords:
                    if keyword not in text:
                        continue

                    # ── 策略 A: 合并文本提取 ────────────────────
                    value_in_text = self._extract_value_from_text(text, keyword, value_pattern)
                    kw_trace_entry = {
                        "keyword": keyword,
                        "ocr_idx": i,
                        "ocr_text": text,
                        "ocr_regions": regions,
                        "in_expected_region": (
                            expected_region in regions if expected_region else None
                        ),
                    }

                    if value_in_text and _is_valid_value(
                        value_in_text, value_pattern,
                        current_field_key=field_key,
                        full_match=field_def.get("full_match", False),
                    ):
                        kw_trace_entry["strategy"] = "merged_text"
                        kw_trace_entry["value_extracted"] = value_in_text
                        if expected_region and expected_region in regions:
                            if not best_region_match[0]:
                                best_region_match = (
                                    value_in_text,
                                    annotated[i][2],
                                    "merged_in_region",
                                )
                        else:
                            if not best_match[0]:
                                best_match = (value_in_text, annotated[i][2], "merged_fallback")
                        field_trace["keywords_tried"].append(kw_trace_entry)
                        break

                    # ── 策略 B: 近邻空间搜索 ────────────────────
                    candidates = self._find_candidates_near_keyword(
                        i,
                        annotated,
                        keyword_box,
                        value_pattern,
                        search_mode,
                    )

                    if candidates:
                        cand_trace = []
                        for dist, cand_text, cand_conf, _cb, cand_strategy in candidates:
                            cand_trace.append(
                                {
                                    "dist": round(dist, 1),
                                    "text": cand_text,
                                    "conf": round(cand_conf, 3),
                                    "strategy": cand_strategy,
                                }
                            )
                        kw_trace_entry["strategy"] = "spatial_search"
                        kw_trace_entry["candidates"] = cand_trace

                        # v4: 筛选有效候选——必须通过 _is_valid_value()
                        valid_candidates = []
                        for dist, cand_text, cand_conf, cand_box, cand_strategy in candidates:
                            cleaned = _clean_value(cand_text)
                            fm = field_def.get("full_match", False)
                            if _is_valid_value(
                                cleaned, value_pattern,
                                current_field_key=field_key,
                                full_match=fm,
                            ):
                                valid_candidates.append(
                                    (dist, cleaned, cand_conf, cand_box, cand_strategy)
                                )

                        if valid_candidates:
                            # 优先取 value_pattern 匹配的
                            pattern_candidates = (
                                [
                                    (d, t, c, b, s)
                                    for d, t, c, b, s in valid_candidates
                                    if value_pattern and re.search(value_pattern, t)
                                ]
                                if value_pattern
                                else []
                            )

                            chosen = (
                                pattern_candidates[0] if pattern_candidates else valid_candidates[0]
                            )
                            chosen_value = chosen[1]  # 已经是 cleaned 值
                            chosen_conf = chosen[2]

                            kw_trace_entry["chosen_candidate"] = {
                                "value": chosen_value,
                                "raw_text": candidates[0][1],
                                "conf": round(chosen_conf, 3),
                                "dist": round(chosen[0], 1),
                                "validated": True,
                            }

                            if expected_region and expected_region in regions:
                                if chosen_conf > best_region_match[1]:
                                    best_region_match = (
                                        chosen_value,
                                        chosen_conf,
                                        "spatial_in_region",
                                    )
                            else:
                                if chosen_conf > best_match[1]:
                                    best_match = (chosen_value, chosen_conf, "spatial_fallback")
                        else:
                            kw_trace_entry["all_candidates_rejected"] = True

                    field_trace["keywords_tried"].append(kw_trace_entry)
                    break

            # ── 最终决策 ──────────────────────────────────────────
            final_match = best_region_match if best_region_match[0] else best_match

            if final_match[0]:
                desensitized = desensitize_field(field_key, final_match[0])
                extracted[field_key] = InvoiceField(
                    key=field_key,
                    label=field_def["label"],
                    value=final_match[0],
                    confidence=final_match[1],
                    desensitized=desensitized,
                )
                field_trace["result"] = "found"
                field_trace["value"] = final_match[0]
                field_trace["conf"] = round(final_match[1], 3)
                field_trace["source"] = final_match[2]
            else:
                field_trace["result"] = "not_found"
                # 兜底：在期望区域搜索匹配 value_pattern 的框
                if value_pattern and expected_region:
                    region_value_trace = self._fallback_region_value_search(
                        annotated,
                        expected_region,
                        value_pattern,
                    )
                    if region_value_trace:
                        field_trace["fallback_region_search"] = region_value_trace
                        # v4: 兜底值也要验证
                        for rv in region_value_trace:
                            cleaned = _clean_value(rv["text"])
                            fm = field_def.get("full_match", False)
                            if _is_valid_value(
                                cleaned, value_pattern,
                                current_field_key=field_key,
                                full_match=fm,
                            ):
                                desensitized = desensitize_field(field_key, cleaned)
                                extracted[field_key] = InvoiceField(
                                    key=field_key,
                                    label=field_def["label"],
                                    value=cleaned,
                                    confidence=rv["conf"],
                                    desensitized=desensitized,
                                )
                                field_trace["result"] = "found_fallback"
                                field_trace["value"] = cleaned
                                field_trace["conf"] = rv["conf"]
                                field_trace["source"] = "region_fallback"
                                break

            if debug:
                trace.append(field_trace)

        groups = self._build_groups(extracted)
        return groups, trace

    def _find_candidates_near_keyword(
        self,
        keyword_idx: int,
        annotated: list[tuple],
        keyword_box: tuple[float, float, float, float],
        value_pattern: str | None,
        search_mode: str,
    ) -> list[tuple[float, str, float, tuple, str]]:
        """搜索关键词附近空间中的候选值框。"""
        keyword_right_x = keyword_box[2]
        keyword_center_y = (keyword_box[1] + keyword_box[3]) / 2

        candidates: list[tuple[float, str, float, tuple, str]] = []

        for j, (_regions, text, conf, box) in enumerate(annotated):
            if j == keyword_idx:
                continue

            cand_center_y = (box[1] + box[3]) / 2
            cand_center_x = (box[0] + box[2]) / 2

            if search_mode == "right":
                y_diff = abs(cand_center_y - keyword_center_y)
                if y_diff > 30:
                    continue
                if cand_center_x < keyword_right_x - 10:
                    continue
                dist = abs(cand_center_x - keyword_right_x)
                candidates.append((dist, text, conf, box, "right_same_line"))

            elif search_mode == "nearby":
                v_diff = cand_center_y - keyword_center_y
                if v_diff < -5:
                    continue
                if v_diff > 120:
                    continue
                if cand_center_x < keyword_box[0] - 50:
                    continue

                dist = _spatial_distance(keyword_box, box)
                y_diff = abs(cand_center_y - keyword_center_y)
                if y_diff <= 30:
                    strategy = "nearby_same_line"
                elif y_diff <= 60:
                    strategy = "nearby_1_line_below"
                else:
                    strategy = "nearby_2_lines_below"
                candidates.append((dist, text, conf, box, strategy))

        candidates.sort(key=lambda x: x[0])
        return candidates

    def _fallback_region_value_search(
        self,
        annotated: list[tuple[list[str], str, float, tuple]],
        expected_region: str,
        value_pattern: str,
    ) -> list[dict] | None:
        """兜底搜索：关键词完全找不到时，在期望区域搜索匹配 value_pattern 的值。"""
        region_matches = []
        for i, (regions, text, conf, _box) in enumerate(annotated):
            if expected_region not in regions:
                continue
            if re.search(value_pattern, text):
                region_matches.append(
                    {"idx": i, "text": text, "conf": round(conf, 3), "regions": regions}
                )
        return region_matches if region_matches else None

    def _extract_value_from_text(
        self,
        text: str,
        keyword: str,
        value_pattern: str | None,
    ) -> str | None:
        """从关键词+值合并识别的文本中提取值。

        v4: 提取后必须通过 _is_valid_value() 验证（在调用方做）。
        v7: 当关键词与完整文本相同时（如"增值税普通发票"），关键词本身就是值。
        """
        kw_pos = text.find(keyword)
        if kw_pos == -1:
            return None

        # v7: 关键词与完整文本相同 → 关键词本身就是值（如发票类型）
        if text.strip() == keyword:
            return keyword

        remaining = text[kw_pos + len(keyword) :].strip()
        remaining = remaining.lstrip(":： \t").strip()

        if not remaining:
            return None

        # 先清洗
        cleaned = _clean_value(remaining)

        if value_pattern:
            match = re.search(value_pattern, cleaned)
            if match:
                return match.group()
            # 不匹配 pattern 的直接返回（调用方会验证）
            return cleaned

        return cleaned

    def _empty_groups(self) -> list[FieldGroup]:
        group_names = [
            "基础信息",
            "金额信息",
            "购方信息",
            "销方信息",
            "出行信息",
            "其他信息",
        ]
        return [FieldGroup(name=name, fields=[]) for name in group_names]

    def _build_groups(self, extracted: dict[str, InvoiceField]) -> list[FieldGroup]:
        group_names = [
            "基础信息",
            "金额信息",
            "购方信息",
            "销方信息",
            "出行信息",
            "其他信息",
        ]
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
    """评估识别结果的可靠性——诚实降级机制。"""
    total_defined = len(FIELD_DEFINITIONS)
    total_extracted = sum(len(g.fields) for g in groups)

    reasons: list[ReliabilityReason] = []

    missing_ratio = 1 - (total_extracted / total_defined)
    if missing_ratio > settings.field_missing_ratio_threshold:
        reasons.append("字段不完整")

    if total_extracted > 0:
        avg_conf = sum(f.confidence for g in groups for f in g.fields) / total_extracted
        if avg_conf < settings.avg_confidence_threshold:
            reasons.append("识别置信度偏低")

    coverage = total_extracted / total_defined
    if coverage < settings.field_coverage_threshold:
        reasons.append("模板匹配不足")

    level: Literal["high", "low"] = "low" if reasons else "high"
    return Reliability(level=level, reasons=reasons)
