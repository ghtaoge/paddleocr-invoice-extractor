"""测试脱敏函数——各种边界和典型值。"""

import pytest

from app.desensitize import (
    desensitize_amount,
    desensitize_company_name,
    desensitize_field,
    desensitize_invoice_number,
    desensitize_tax_number,
)


class TestInvoiceNumber:
    """发票号码脱敏——中间 4 位遮蔽。"""

    def test_eight_digit(self) -> None:
        assert desensitize_invoice_number("12345678") == "12****78"

    def test_long_number(self) -> None:
        assert desensitize_invoice_number("123456789012") == "12****12"

    def test_short_value(self) -> None:
        # 短于 4 位不做遮蔽
        assert desensitize_invoice_number("123") == "123"

    def test_four_digit(self) -> None:
        # 4 位不做遮蔽（≤ 4）
        assert desensitize_invoice_number("1234") == "1234"

    def test_five_digit(self) -> None:
        assert desensitize_invoice_number("12345") == "12****45"


class TestTaxNumber:
    """税号脱敏——后半段遮蔽。"""

    def test_eighteen_digit(self) -> None:
        # 18 位：前 9 位 + ****
        assert desensitize_tax_number("91110000MA01ABCDEF") == "91110000M****"

    def test_short_value(self) -> None:
        assert desensitize_tax_number("123") == "123"

    def test_odd_length(self) -> None:
        # 7 位：前 3 位 + ****
        assert desensitize_tax_number("1234567") == "123****"


class TestCompanyName:
    """公司名称脱敏——首尾各保留 2 字。"""

    def test_long_name(self) -> None:
        assert desensitize_company_name("北京某某科技有限公司") == "北京****公司"

    def test_short_name(self) -> None:
        assert desensitize_company_name("公司") == "公司"

    def test_four_char(self) -> None:
        # 4 字不做遮蔽
        assert desensitize_company_name("某某公司") == "某某公司"

    def test_five_char(self) -> None:
        assert desensitize_company_name("某某某公司") == "某某****公司"


class TestAmount:
    """金额脱敏——保留整数部分。"""

    def test_with_decimal(self) -> None:
        assert desensitize_amount("12345.67") == "12345.****"

    def test_integer(self) -> None:
        assert desensitize_amount("12345") == "12345"

    def test_small_decimal(self) -> None:
        assert desensitize_amount("0.05") == "0.****"


class TestFieldDesensitize:
    """字段脱敏映射——按 key 选择函数。"""

    def test_mapped_field(self) -> None:
        assert desensitize_field("invoice_number", "12345678") == "12****78"

    def test_unmapped_field(self) -> None:
        # 不在映射中的字段原样返回
        assert desensitize_field("invoice_date", "2026年01月") == "2026年01月"

    def test_tax_rate_unmapped(self) -> None:
        assert desensitize_field("tax_rate", "13%") == "13%"
