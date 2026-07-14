"""测试 OCR 引擎——使用假引擎避免下载真实模型。"""

import io

import pytest
from PIL import Image

from app.config import Settings
from app.errors import AppError
from app.ocr import OCRRunner


class FakeOCR:
    """假 PaddleOCR——返回固定的识别结果。"""

    def ocr(self, img_array, cls=True):
        # 返回模拟的发票识别结果
        return [
            [
                [
                    [[100, 200], [200, 200], [200, 220], [100, 220]],
                    ("发票号码", 0.98),
                ],
                [
                    [[210, 200], [300, 200], [300, 220], [210, 220]],
                    ("12345678", 0.95),
                ],
            ]
        ]


class FakeEmptyOCR:
    """假 PaddleOCR——返回空结果（模拟未检测到文字）。"""

    def ocr(self, img_array, cls=True):
        return None


class FakeErrorOCR:
    """假 PaddleOCR——模拟识别失败。"""

    def ocr(self, img_array, cls=True):
        raise RuntimeError("OCR error")


def _make_test_jpeg() -> bytes:
    """创建一个小的 JPEG 图片字节用于测试。"""
    img = Image.new("RGB", (400, 300), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestOCRRunnerInit:
    """初始化行为。"""

    def test_initial_status(self) -> None:
        runner = OCRRunner(Settings())
        assert runner.status == "not_loaded"

    def test_device_default_cpu(self) -> None:
        runner = OCRRunner(Settings())
        assert runner.device == "cpu"


class TestOCRRunnerLoad:
    """模型加载。"""

    def test_manual_load_sets_status(self) -> None:
        runner = OCRRunner(Settings())
        runner._ocr = FakeOCR()
        runner._status = "loaded"
        assert runner.status == "loaded"

    def test_double_load_no_error(self) -> None:
        runner = OCRRunner(Settings())
        runner._ocr = FakeOCR()
        runner._status = "loaded"
        # 再次调用 load 不应出错（快速路径）
        runner.load()
        assert runner.status == "loaded"


class TestOCRRunnerRun:
    """OCR 识别。"""

    def test_run_with_fake_engine(self) -> None:
        runner = OCRRunner(Settings())
        runner._ocr = FakeOCR()
        runner._status = "loaded"

        image_bytes = _make_test_jpeg()
        results = runner.run(image_bytes, "jpg")
        assert len(results) == 2
        # 第一项应该是 (rect, text, confidence)
        assert results[0][1] == "发票号码"
        assert results[0][2] == 0.98

    def test_run_empty_result(self) -> None:
        """PaddleOCR 返回空结果时应返回空列表。"""
        runner = OCRRunner(Settings())
        runner._ocr = FakeEmptyOCR()
        runner._status = "loaded"

        image_bytes = _make_test_jpeg()
        results = runner.run(image_bytes, "jpg")
        assert results == []

    def test_run_raises_on_error(self) -> None:
        """OCR 识别失败时应抛出 OCR_FAILED。"""
        runner = OCRRunner(Settings())
        runner._ocr = FakeErrorOCR()
        runner._status = "loaded"

        image_bytes = _make_test_jpeg()
        with pytest.raises(AppError) as exc_info:
            runner.run(image_bytes, "jpg")
        assert exc_info.value.code == "OCR_FAILED"
