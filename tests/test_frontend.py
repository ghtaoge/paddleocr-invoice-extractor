"""测试前端文件存在性和基本结构。"""

import pytest
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"

ICON_NAMES = [
    "upload.svg",
    "trash-2.svg",
    "eye.svg",
    "eye-off.svg",
    "download.svg",
    "file-json.svg",
    "file-text.svg",
    "search.svg",
    "check.svg",
]


class TestStaticFiles:
    """前端静态文件应全部存在。"""

    def test_index_html(self) -> None:
        assert (STATIC_DIR / "index.html").is_file()

    def test_styles_css(self) -> None:
        assert (STATIC_DIR / "styles.css").is_file()

    def test_app_js(self) -> None:
        assert (STATIC_DIR / "app.js").is_file()


class TestIcons:
    """SVG 图标应全部存在。"""

    @pytest.mark.parametrize("icon", ICON_NAMES)
    def test_icon_exists(self, icon: str) -> None:
        assert (STATIC_DIR / "icons" / icon).is_file()


class TestHtmlStructure:
    """HTML 应包含关键结构元素。"""

    def test_contains_brand(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "票析" in html
        assert "增值税发票识别" in html

    def test_contains_upload_zone(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "dropzone" in html.lower() or "上传" in html

    def test_contains_privacy_notice(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "隐私" in html or "不保存" in html or "不上传" in html

    def test_contains_export_buttons(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "JSON" in html or "导出" in html

    def test_contains_app_js_reference(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "app.js" in html


class TestCssDesignSystem:
    """CSS 应包含关键设计系统变量。"""

    def test_contains_vermilion(self) -> None:
        css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        assert "#c63c2f" in css

    def test_contains_paper_color(self) -> None:
        css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        assert "#f5f4ef" in css

    def test_contains_responsive_breakpoint(self) -> None:
        css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        assert "860" in css


class TestJsApiCalls:
    """JS 应包含关键 API 调用。"""

    def test_contains_health_check(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        assert "/api/health" in js

    def test_contains_ocr_api(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        assert "/api/ocr" in js

    def test_contains_export_function(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        assert "JSON" in js or "export" in js.lower()
