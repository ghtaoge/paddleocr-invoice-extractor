"""票析 — FastAPI 应用入口

创建应用实例、注册路由和异常处理、挂载静态文件。
采用工厂模式支持依赖注入——测试时可注入假服务。"""

from __future__ import annotations

import threading
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from app.config import Settings, get_settings
from app.errors import (
    AppError,
    CONCURRENT_REQUEST,
    FILE_TOO_LARGE,
    INTERNAL_ERROR,
    NO_TEXT_DETECTED,
    UNSUPPORTED_FORMAT,
)
from app.ocr import OCRRunner
from app.schemas import (
    HealthResponse,
    InvoiceResult,
    PublicError,
    Reliability,
)
from app.template import InvoiceTemplate, evaluate_reliability

# ── 静态文件目录 ──────────────────────────────────────────────
STATIC_DIR = Path(__file__).resolve().parent / "static"


class Services:
    """服务容器——聚合 OCRRunner 和 InvoiceTemplate。"""

    def __init__(self, ocr: OCRRunner, template: InvoiceTemplate) -> None:
        self.ocr = ocr
        self.template = template


def create_app(
    settings: Settings | None = None,
    services: Services | None = None,
) -> FastAPI:
    """创建 FastAPI 应用——支持注入假服务和自定义配置。"""
    if settings is None:
        settings = get_settings()
    if services is None:
        services = Services(
            ocr=OCRRunner(settings),
            template=InvoiceTemplate(),
        )

    application = FastAPI(
        title="票析 · 增值税发票识别",
        docs_url=None,
        redoc_url=None,
    )

    # ── 将服务和配置绑定到 app.state ──────────────────────────
    application.state.settings = settings
    application.state.services = services
    application.state.analysis_lock = threading.Lock()

    # ── 异常处理 ────────────────────────────────────────────────
    @application.exception_handler(AppError)
    async def handle_app_error(
        request: Request,
        exc: AppError,
    ) -> JSONResponse:
        """将 AppError 转为 JSON 响应——只暴露 code 和 public_message。"""
        body = PublicError(code=exc.code, message=exc.public_message)
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(),
        )

    # ── 路由 ────────────────────────────────────────────────────
    @application.get("/")
    async def index() -> FileResponse:
        """返回主页面。"""
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/api/health")
    async def health() -> HealthResponse:
        """健康检查——返回服务状态、模型状态和推理设备。"""
        svc = application.state.services
        return HealthResponse(
            status="ok",
            model_status=svc.ocr.status,
            device=svc.ocr.device,
        )

    @application.post("/api/ocr")
    async def recognize(file: UploadFile) -> InvoiceResult:
        """发票识别——上传图片，返回结构化字段结果。"""
        svc = application.state.services
        settings: Settings = application.state.settings

        # ── 并发控制：同一时间只处理一个请求 ──────────────────
        if not application.state.analysis_lock.acquire(blocking=False):
            raise CONCURRENT_REQUEST

        try:
            # ── 读取文件字节 ────────────────────────────────────
            image_bytes = await file.read()

            # ── 大小校验 ────────────────────────────────────────
            if len(image_bytes) > settings.max_file_bytes:
                raise FILE_TOO_LARGE

            # ── 格式校验 ────────────────────────────────────────
            ext = (file.filename or "").rsplit(".", 1)[-1].lower()
            if ext not in settings.supported_formats:
                raise UNSUPPORTED_FORMAT

            # ── OCR 识别 ────────────────────────────────────────
            ocr_results = svc.ocr.run(image_bytes, ext)

            if not ocr_results:
                raise NO_TEXT_DETECTED

            # ── 获取图片尺寸（用于区域定位）────────────────────
            img = Image.open(BytesIO(image_bytes))
            image_height = img.size[1]

            # ── 模板映射 ────────────────────────────────────────
            groups = svc.template.map_results(ocr_results, image_height)

            # ── 可靠性评估 ────────────────────────────────────────
            reliability = evaluate_reliability(groups, settings)

            # ── 计算整体置信度 ────────────────────────────────────
            total_fields = sum(len(g.fields) for g in groups)
            if total_fields > 0:
                avg_conf = sum(
                    f.confidence for g in groups for f in g.fields
                ) / total_fields
            else:
                avg_conf = 0.0

            # ── 构建响应 ────────────────────────────────────────
            boxes = [
                {"box": list(r[0]), "text": r[1], "confidence": r[2]}
                for r in ocr_results
            ]

            return InvoiceResult(
                groups=groups,
                overall_confidence=avg_conf,
                reliability=reliability,
                device=svc.ocr.device,
                ocr_boxes=boxes,
            )

        except AppError:
            raise  # 已知业务异常，直接抛给异常处理器
        except Exception:
            raise INTERNAL_ERROR from None
        finally:
            application.state.analysis_lock.release()

    # ── 挂载静态文件 ────────────────────────────────────────────
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)))

    return application


# ── 模块级实例——供 uvicorn 直接使用 ────────────────────────────
app = create_app()
