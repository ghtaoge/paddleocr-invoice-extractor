"""票析 — 业务异常

所有业务错误统一使用 AppError，包含机器可读 code、
面向用户的中文 public_message 和 HTTP status_code。
内部调试信息不暴露给调用方。"""


class AppError(Exception):
    """业务异常——code 供程序判断，public_message 供用户阅读。"""

    def __init__(
        self,
        code: str,
        public_message: str,
        status_code: int = 400,
    ) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message
        self.status_code = status_code


# ── 预定义错误常量 ────────────────────────────────────────────
FILE_TOO_LARGE = AppError(
    code="FILE_TOO_LARGE",
    public_message="上传文件超过大小限制",
    status_code=413,
)

UNSUPPORTED_FORMAT = AppError(
    code="UNSUPPORTED_FORMAT",
    public_message="不支持该图片格式",
    status_code=415,
)

OCR_FAILED = AppError(
    code="OCR_FAILED",
    public_message="图片识别失败，请确认图片清晰度",
    status_code=422,
)

NO_TEXT_DETECTED = AppError(
    code="NO_TEXT_DETECTED",
    public_message="图片中未检测到文字",
    status_code=422,
)

CONCURRENT_REQUEST = AppError(
    code="CONCURRENT_REQUEST",
    public_message="正在处理中，请稍后再试",
    status_code=429,
)

INTERNAL_ERROR = AppError(
    code="INTERNAL_ERROR",
    public_message="服务内部错误",
    status_code=500,
)
