"""票析 — PaddleOCR 引擎封装

模型懒加载、单例管理、设备自动选择。
首次识别时自动下载 PP-OCRv4 模型权重（约 10 MB），
后续识别复用本地缓存。"""

from __future__ import annotations

import threading
from io import BytesIO

import numpy as np
from PIL import Image

from app.config import Settings
from app.errors import OCR_FAILED


class OCRRunner:
    """PaddleOCR 引擎——懒加载单例，线程安全。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ocr: object | None = None  # PaddleOCR 实例
        self._lock = threading.Lock()
        self._device: str = "cpu"  # 默认 CPU，实际加载时检测
        self._status: str = "not_loaded"

    # ── 模型加载 ────────────────────────────────────────────────
    def load(self) -> None:
        """加载 PaddleOCR 模型——双重检查锁定防止并发加载。"""
        # 快速路径：已加载则直接返回
        if self._ocr is not None:
            return

        with self._lock:
            # 再次检查——可能在等待锁期间被其他线程加载
            if self._ocr is not None:
                return

            self._status = "loading"
            try:
                from paddleocr import PaddleOCR

                self._ocr = PaddleOCR(
                    use_angle_cls=self._settings.ocr_use_angle_cls,
                    use_gpu=self._settings.ocr_use_gpu,
                    lang="ch",
                    show_log=False,
                )
                self._status = "loaded"

                # ── 检测实际使用的设备 ────────────────────────
                try:
                    import paddle
                    if paddle.device.get_device() != "cpu":
                        self._device = "cuda"
                    else:
                        self._device = "cpu"
                except Exception:
                    self._device = "cpu"

            except Exception:
                self._status = "error"
                raise

    # ── 推理 ────────────────────────────────────────────────────
    def run(
        self,
        image_bytes: bytes,
        format: str,
    ) -> list[tuple]:
        """对图片执行 OCR 识别——返回检测框、文本和置信度列表。

        参数：
            image_bytes: 图片原始字节
            format: 图片格式（jpg/png/bmp）

        返回：list[((x1,y1,x2,y2), text, confidence), ...]
        """
        # 确保模型已加载
        self.load()

        try:
            # 将字节转为 PIL Image 再转为 numpy 数组
            img = Image.open(BytesIO(image_bytes))
            img_array = np.array(img)

            # 调用 PaddleOCR
            result = self._ocr.ocr(img_array, cls=True)

            if not result or not result[0]:
                return []

            # 转换 PaddleOCR 输出格式
            # PaddleOCR 返回: [[[box], (text, confidence)], ...]
            processed: list[tuple] = []
            for line in result[0]:
                box = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text = line[1][0]
                confidence = line[1][1]

                # 将四点坐标转为 (x1, y1, x2, y2) 矩形格式
                x_coords = [p[0] for p in box]
                y_coords = [p[1] for p in box]
                rect = (
                    min(x_coords),
                    min(y_coords),
                    max(x_coords),
                    max(y_coords),
                )
                processed.append((rect, text, confidence))

            return processed

        except Exception as exc:
            raise OCR_FAILED from exc

    # ── 状态访问 ────────────────────────────────────────────────
    @property
    def status(self) -> str:
        return self._status

    @property
    def device(self) -> str:
        return self._device
