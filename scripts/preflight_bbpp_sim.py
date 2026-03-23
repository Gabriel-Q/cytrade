"""BBPP 模拟盘启动前自检脚本。

目标：在真正启动模拟盘前，尽可能提前暴露环境问题，减少盘中才发现配置错误。
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import Settings
from strategy.bbpp_strategy import BbppStrategy


def _check_package(name: str) -> tuple[bool, str]:
    """检查关键依赖是否可导入。"""
    try:
        importlib.import_module(name)
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def _print_result(title: str, ok: bool, detail: str) -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {title}: {detail}")
    return ok


def main() -> int:
    """执行 BBPP 模拟盘启动前自检。"""
    settings = Settings()
    checks_ok = True

    qmt_path = Path(settings.QMT_PATH).expanduser() if settings.QMT_PATH else None
    bbpp_csv = BbppStrategy._default_csv_path()

    print("BBPP 模拟盘自检开始")
    print("工作目录:", ROOT)
    print("BBPP CSV:", bbpp_csv)

    checks_ok &= _print_result("Python 依赖 xtquant", *_check_package("xtquant"))
    checks_ok &= _print_result("Python 依赖 talib", *_check_package("talib"))
    checks_ok &= _print_result("Python 依赖 fastapi", *_check_package("fastapi"))

    checks_ok &= _print_result(
        "QMT_PATH 已配置",
        bool(settings.QMT_PATH),
        settings.QMT_PATH or "未设置环境变量 QMT_PATH",
    )
    if settings.QMT_PATH:
        checks_ok &= _print_result(
            "QMT_PATH 路径存在",
            bool(qmt_path and qmt_path.exists()),
            str(qmt_path),
        )

    checks_ok &= _print_result(
        "ACCOUNT_ID 已配置",
        bool(settings.ACCOUNT_ID),
        settings.ACCOUNT_ID or "未设置环境变量 ACCOUNT_ID",
    )
    checks_ok &= _print_result(
        "费率表存在",
        Path(settings.FEE_TABLE_PATH).exists(),
        settings.FEE_TABLE_PATH,
    )
    checks_ok &= _print_result(
        "BBPP CSV 存在",
        bbpp_csv.exists(),
        str(bbpp_csv),
    )

    print("默认 Web 端口:", settings.WEB_PORT)
    print("模拟盘单标的测试脚本默认端口: 8081")

    if checks_ok:
        print("自检通过，可以进入下一步模拟盘测试。")
        return 0

    print("自检未通过，请先修复 FAIL 项后再启动模拟盘。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())