"""票析 — 隐私扫描脚本

检测 Git 仓库中的隐私泄漏风险：
1. 禁止提交的二进制文件（图片、模型权重等）
2. PEM 格式私钥
3. Bearer Token
4. Windows/POSIX 路径泄漏
5. 真实公司名称（增值税发票特有风险）"""

import re
import subprocess
import sys
import warnings

# ── 禁止提交的文件后缀 ────────────────────────────────────────
BLOCKED_SUFFIXES = frozenset({
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".gif",  # 图片文件
    ".bin", ".pdparams", ".pdiparams", ".onnx",  # 模型权重
    ".wav", ".mp3", ".m4a", ".flac",  # 音频文件
})

# ── 正则扫描规则 ──────────────────────────────────────────────
PRIVATE_KEY = re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")
BEARER_TOKEN = re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}")
WINDOWS_HOME = re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+")
POSIX_HOME = re.compile(r"/home/[^/\s]+")
# ── 真实公司名称 ────────────────────────────────────────────────
# 检测常见中国公司名称模式——排除含占位符"某"的合成假名称
# 使用否定前瞻排除含"某"字的公司名
REAL_COMPANY = re.compile(
    r"(北京|上海|广州|深圳|杭州|南京|成都|武汉)"
    r"(?!某某)"  # 排除"某某"占位符
    r"[一-鿿]{2,8}"
    r"(有限公司|股份有限公司|集团)"
)

# ── 排除路径 ────────────────────────────────────────────────────
# 这些文件不扫描（文档和配置中允许包含示例路径）
EXCLUDE_PATHS = frozenset({
    "README.md",
    "README_en.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".env.example",
})


def tracked_files() -> list[str]:
    """获取 Git 仓库中所有跟踪的文件路径。"""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=False,
    )
    paths = result.stdout.decode("utf-8", errors="replace").split("\0")
    return [p for p in paths if p.strip()]


def scan_content(content: str, path: str) -> list[str]:
    """扫描文件内容中的隐私风险。"""
    findings: list[str] = []

    # 跳过排除路径
    if path in EXCLUDE_PATHS:
        return findings

    if PRIVATE_KEY.search(content):
        findings.append(f"{path}: 发现 PEM 私钥")
    if BEARER_TOKEN.search(content):
        findings.append(f"{path}: 发现 Bearer Token")
    if WINDOWS_HOME.search(content):
        findings.append(f"{path}: 发现 Windows 用户路径")
    if POSIX_HOME.search(content):
        findings.append(f"{path}: 发现 POSIX 用户路径")
    # 真实公司名称扫描——排除文档和配置示例
    if REAL_COMPANY.search(content):
        findings.append(f"{path}: 可能包含真实公司名称")

    return findings


def main() -> int:
    """主扫描逻辑——返回 0（干净）或 1（有发现）。"""
    all_findings: list[str] = []

    for path in tracked_files():
        # ── 后缀检查 ────────────────────────────────────────
        suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if f".{suffix}" in BLOCKED_SUFFIXES:
            all_findings.append(f"{path}: 禁止提交的文件类型 (.{suffix})")
            continue

        # ── 内容扫描 ────────────────────────────────────────
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except (UnicodeDecodeError, OSError):
            continue  # 二进制文件或不可读——跳过

        findings = scan_content(content, path)
        all_findings.extend(findings)

    if all_findings:
        for finding in all_findings:
            print(f"[!] {finding}")
        print(f"\n共发现 {len(all_findings)} 个隐私风险")
        return 1

    print("[OK] 隐私扫描通过——未发现风险")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
