"""测试 FastAPI 端点——使用假服务避免真实 OCR 调用。"""

import io

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import Services, create_app
from app.ocr import OCRRunner
from app.template import InvoiceTemplate


class FakeOCRRunner:
    """假 OCRRunner——返回固定结果。"""

    @property
    def status(self) -> str:
        return "loaded"

    @property
    def device(self) -> str:
        return "cpu"

    def load(self) -> None:
        pass

    def run(self, image_bytes: bytes, format: str) -> list[tuple]:
        return [
            ((100, 200, 200, 220), "发票号码", 0.98),
            ((210, 200, 300, 220), "12345678", 0.95),
        ]


class FakeEmptyOCRRunner:
    """假 OCRRunner——返回空结果。"""

    @property
    def status(self) -> str:
        return "loaded"

    @property
    def device(self) -> str:
        return "cpu"

    def load(self) -> None:
        pass

    def run(self, image_bytes: bytes, format: str) -> list[tuple]:
        return []


def _make_test_jpeg() -> bytes:
    """创建一个小的 JPEG 图片字节用于测试。"""
    img = Image.new("RGB", (400, 300), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _create_test_app(services: Services | None = None) -> TestClient:
    """创建测试客户端——注入假服务。"""
    if services is None:
        services = Services(
            ocr=FakeOCRRunner(),
            template=InvoiceTemplate(),
        )
    app = create_app(settings=Settings(), services=services)
    return TestClient(app)


class TestHealth:
    """健康检查端点。"""

    def test_health_ok(self) -> None:
        client = _create_test_app()
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["model_status"] == "loaded"
        assert data["device"] == "cpu"


class TestRecognize:
    """发票识别端点。"""

    def test_recognize_success(self) -> None:
        client = _create_test_app()
        img_bytes = _make_test_jpeg()
        resp = client.post(
            "/api/ocr",
            files={"file": ("test.jpg", img_bytes, "image/jpeg")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data
        assert "overall_confidence" in data
        assert "reliability" in data
        assert "ocr_boxes" in data

    def test_recognize_no_text(self) -> None:
        """未检测到文字时应返回 422。"""
        services = Services(
            ocr=FakeEmptyOCRRunner(),
            template=InvoiceTemplate(),
        )
        client = _create_test_app(services)
        img_bytes = _make_test_jpeg()
        resp = client.post(
            "/api/ocr",
            files={"file": ("test.jpg", img_bytes, "image/jpeg")},
        )
        assert resp.status_code == 422

    def test_recognize_file_too_large(self) -> None:
        """文件过大时应返回 413。"""
        client = _create_test_app()
        # 创建超过默认 10MB 限制的假数据
        big_data = b"x" * (11 * 1024 * 1024)
        resp = client.post(
            "/api/ocr",
            files={"file": ("test.jpg", big_data, "image/jpeg")},
        )
        assert resp.status_code == 413

    def test_recognize_unsupported_format(self) -> None:
        """不支持格式应返回 415。"""
        client = _create_test_app()
        resp = client.post(
            "/api/ocr",
            files={"file": ("test.tiff", _make_test_jpeg(), "image/tiff")},
        )
        assert resp.status_code == 415
