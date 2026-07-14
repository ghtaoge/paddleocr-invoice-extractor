"""票析 — 应用配置

从环境变量和 .env 文件加载设置。设置对象冻结后不可修改，
通过 lru_cache 实现进程级单例。"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── 约束类型别名 ──────────────────────────────────────────────
Port = Annotated[int, Field(gt=0, le=65535)]
PositiveInt = Annotated[int, Field(gt=0)]
PositiveFloat = Annotated[float, Field(gt=0)]


class Settings(BaseSettings):
    """应用配置——所有值均可通过同名环境变量覆盖。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        frozen=True,
    )

    # ── 服务器 ────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: Port = 8000

    # ── 文件限制 ──────────────────────────────────────────────
    max_file_bytes: PositiveInt = 10 * 1024 * 1024  # 10 MB
    supported_formats: list[Literal["jpg", "jpeg", "png", "bmp"]] = [
        "jpg",
        "jpeg",
        "png",
        "bmp",
    ]

    # ── PaddleOCR ─────────────────────────────────────────────
    ocr_use_angle_cls: bool = True
    ocr_use_gpu: bool = False  # 默认 CPU，有 CUDA 时可通过环境变量开启

    # ── 模板置信度阈值 ────────────────────────────────────────
    field_missing_ratio_threshold: PositiveFloat = 0.30
    avg_confidence_threshold: PositiveFloat = 0.80
    field_coverage_threshold: PositiveFloat = 0.60

    @field_validator("host")
    @classmethod
    def reject_blank_strings(cls, v: str) -> str:
        """拒绝空白字符串——防止误配置空主机名。"""
        if not v.strip():
            raise ValueError("不能为空白字符串")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回进程级配置单例——lru_cache 保证只创建一次。"""
    return Settings()
