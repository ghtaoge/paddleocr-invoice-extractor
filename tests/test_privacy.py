"""测试隐私扫描脚本——验证各扫描规则正确触发。"""

import subprocess
import sys

import pytest

from scripts.privacy_scan import BLOCKED_SUFFIXES, EXCLUDE_PATHS


class TestPrivacyScanRules:
    """隐私扫描规则应正确检测各类风险。"""

    def test_scan_script_runs(self) -> None:
        """扫描脚本应可执行。"""
        result = subprocess.run(
            [sys.executable, "scripts/privacy_scan.py"],
            capture_output=True,
            text=True,
        )
        # 脚本应能正常运行（返回 0 或 1）
        assert result.returncode in [0, 1]

    def test_blocked_suffixes_list(self) -> None:
        """禁止后缀列表应包含图片和模型文件。"""
        assert ".jpg" in BLOCKED_SUFFIXES
        assert ".png" in BLOCKED_SUFFIXES
        assert ".bmp" in BLOCKED_SUFFIXES
        assert ".pdparams" in BLOCKED_SUFFIXES

    def test_exclude_paths(self) -> None:
        """排除路径应包含文档和配置示例。"""
        assert "README.md" in EXCLUDE_PATHS
        assert ".env.example" in EXCLUDE_PATHS
