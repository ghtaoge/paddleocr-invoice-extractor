"""票析 — 脱敏工具

对发票敏感字段进行遮蔽处理——前端展示时使用脱敏版本，
导出文件保留完整数据。遮蔽规则：
- 发票号码：中间 4 位替换为 ****
- 税号/识别号：后半段替换为 ****
- 公司名称：首尾各保留 2 字，中间替换为 ****
- 金额：保留整数部分，小数部分替换为 ****"""


def desensitize_invoice_number(value: str) -> str:
    """发票号码脱敏——中间 4 位遮蔽。

    示例：12345678 → 12****78（至少 8 位时遮蔽中间 4 位）
    短于 4 位的值不做遮蔽。
    """
    if len(value) <= 4:
        return value
    # 保留前 2 位和后 2 位，中间替换为 ****
    return value[:2] + "****" + value[-2:]


def desensitize_tax_number(value: str) -> str:
    """纳税人识别号脱敏——后半段遮蔽。

    示例：91110000MA01ABCDEF → 91110000M****
    短于 4 位的值不做遮蔽。
    """
    if len(value) <= 4:
        return value
    half = len(value) // 2
    return value[:half] + "****"


def desensitize_company_name(value: str) -> str:
    """公司名称脱敏——首尾各保留 2 字，中间遮蔽。

    示例：北京某某科技有限公司 → 北京****公司
    短于 4 字的名称不做遮蔽。
    """
    if len(value) <= 4:
        return value
    return value[:2] + "****" + value[-2:]


def desensitize_amount(value: str) -> str:
    """金额脱敏——保留整数部分，小数部分遮蔽。

    示例：12345.67 → 12345.****
    不含小数点的金额不做遮蔽。
    """
    dot_pos = value.find(".")
    if dot_pos == -1:
        return value
    return value[: dot_pos + 1] + "****"


# ── 字段脱敏映射 ──────────────────────────────────────────────
# 按字段 key 选择对应的脱敏函数
FIELD_DESENSITIZE_MAP: dict[str, callable] = {
    "invoice_number": desensitize_invoice_number,
    "invoice_code": desensitize_invoice_number,
    "check_code": desensitize_invoice_number,
    "buyer_tax_number": desensitize_tax_number,
    "seller_tax_number": desensitize_tax_number,
    "buyer_name": desensitize_company_name,
    "seller_name": desensitize_company_name,
    "buyer_address_phone": desensitize_company_name,
    "seller_address_phone": desensitize_company_name,
    "buyer_bank_account": desensitize_company_name,
    "seller_bank_account": desensitize_company_name,
    "amount_without_tax": desensitize_amount,
    "tax_amount": desensitize_amount,
    "amount_with_tax": desensitize_amount,
}


def desensitize_field(key: str, value: str) -> str:
    """按字段类型选择脱敏函数——不在映射中的字段原样返回。"""
    func = FIELD_DESENSITIZE_MAP.get(key)
    if func is None:
        return value
    return func(value)
