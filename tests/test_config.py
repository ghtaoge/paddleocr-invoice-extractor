"""测试应用配置——校验、缓存、冻结行为。"""

import os
from functools import lru_cache

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


class TestDefaults:
    """默认值不应意外改变——它们也是公开行为。"""

    def test_default_port(self) -> None:
        s = Settings()
        assert s.port == 8000

    def test_default_host(self) -> None:
        s = Settings()
        assert s.host == "127.0.0.1"

    def test_default_max_bytes(self) -> None:
        s = Settings()
        assert s.max_file_bytes == 10 * 1024 * 1024

    def test_default_formats(self) -> None:
        s = Settings()
        assert s.supported_formats == ["jpg", "jpeg", "png", "bmp"]


class TestValidation:
    """边界值和非法输入应被拒绝。"""

    def test_reject_blank_host(self) -> None:
        with pytest.raises(ValidationError, match="不能为空白字符串"):
            Settings(host="   ")

    def test_reject_zero_port(self) -> None:
        with pytest.raises(ValidationError):
            Settings(port=0)

    def test_reject_negative_port(self) -> None:
        with pytest.raises(ValidationError):
            Settings(port=-1)

    def test_reject_zero_max_bytes(self) -> None:
        with pytest.raises(ValidationError):
            Settings(max_file_bytes=0)

    def test_reject_negative_max_bytes(self) -> None:
        with pytest.raises(ValidationError):
            Settings(max_file_bytes=-1)


class TestEnvOverride:
    """环境变量应能覆盖默认值。"""

    def test_env_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "9000")
        s = Settings()
        assert s.port == 9000


class TestFrozen:
    """设置对象冻结后不应允许赋值。"""

    def test_frozen(self) -> None:
        s = Settings()
        with pytest.raises(ValidationError):
            s.port = 9999  # type: ignore[misc]


class TestSingleton:
    """get_settings 应返回同一个对象。"""

    def test_singleton(self) -> None:
        # lru_cache 在测试中可能已缓存旧值——先清除
        get_settings.cache_clear()
        a = get_settings()
        b = get_settings()
        assert a is b
