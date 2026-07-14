"""测试业务异常类——字段值和 HTTP 状态码。"""

from app.errors import (
    AppError,
    FILE_TOO_LARGE,
    INTERNAL_ERROR,
    OCR_FAILED,
    UNSUPPORTED_FORMAT,
)


class TestAppError:
    """AppError 应正确存储三个字段。"""

    def test_fields(self) -> None:
        err = AppError("TEST_CODE", "测试消息", 418)
        assert err.code == "TEST_CODE"
        assert err.public_message == "测试消息"
        assert err.status_code == 418

    def test_default_status_code(self) -> None:
        err = AppError("CODE", "msg")
        assert err.status_code == 400

    def test_exception_inherits(self) -> None:
        err = AppError("CODE", "msg")
        assert isinstance(err, Exception)

    def test_predefined_constants(self) -> None:
        assert FILE_TOO_LARGE.code == "FILE_TOO_LARGE"
        assert FILE_TOO_LARGE.status_code == 413
        assert UNSUPPORTED_FORMAT.code == "UNSUPPORTED_FORMAT"
        assert UNSUPPORTED_FORMAT.status_code == 415
        assert OCR_FAILED.code == "OCR_FAILED"
        assert OCR_FAILED.status_code == 422
        assert INTERNAL_ERROR.code == "INTERNAL_ERROR"
        assert INTERNAL_ERROR.status_code == 500
