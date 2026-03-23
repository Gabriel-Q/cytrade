"""BBPP 单标的模拟盘烟雾测试脚本。

这个脚本的目标不是回测，而是把“生成一份独立的 BBPP CSV + 启动真实框架”
这两件事一次性做好，方便下一步直接在 QMT 模拟盘里验证：

1. 策略能否正常读取候选 CSV。
2. 历史数据和指标能否顺利预热。
3. Runner / Web / 订单 / 持仓链路能否完整跑通。

默认行为：
- 自动为单个测试标的生成运行期 CSV。
- 通过环境变量把策略指向该临时 CSV。
- 使用独立的日志、状态和 SQLite 目录，避免污染正式运行目录。
- 启动后进入正常交易运行态，按 Ctrl+C 退出。
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import Settings
from core.history_data import HistoryDataManager
from core.trading_calendar import minus_one_market_day, shift_market_day
from main import run
from strategy.bbpp_strategy import BbppStrategy


def _normalize_trade_day(value) -> str:
    """把历史数据里的时间字段规范成 YYYYMMDD。"""
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else text


def _prepare_history_frame(frame):
    """把 xtquant 返回的历史数据整理成按交易日排序的 DataFrame。

    逻辑说明：
    1. 兼容 ``trade_date`` / ``time`` / ``date`` / index 等多种日期来源。
    2. 只保留 OHLCV 和交易日字段，便于后续选取最近几个锚点日期。
    3. 返回按交易日升序排列的数据。
    """
    import pandas as pd

    if frame is None or frame.empty:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])

    df = frame.copy()
    if "trade_date" in df.columns:
        trade_dates = df["trade_date"]
    elif "time" in df.columns:
        trade_dates = df["time"]
    elif "date" in df.columns:
        trade_dates = df["date"]
    else:
        trade_dates = df.index

    df["trade_date"] = [ _normalize_trade_day(value) for value in trade_dates ]
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = df[column].astype(float)
    df = df[df["trade_date"].astype(bool)].copy()
    df = df.drop_duplicates(subset=["trade_date"], keep="last").sort_values("trade_date")
    return df.reset_index(drop=True)


def build_smoketest_row(stock_code: str, buy_method: str = "d") -> dict:
    """根据最近历史数据自动生成一行可用于 BBPP 的测试配置。

    逻辑说明：
    1. 先下载并读取最近 90 个交易日的日线数据。
    2. 取最近 4~5 个有效交易日作为锚点日期，保证日期新、价格接近当前市场。
    3. 默认用 ``d`` 方法，这样参考建仓价直接取锚点开盘价，更适合模拟盘快速验证挂单。
    """
    history_mgr = HistoryDataManager()
    end_date = minus_one_market_day(datetime.now().strftime("%Y%m%d"))
    start_date = shift_market_day(end_date, -90)
    frames = history_mgr.get_history_data(
        stock_list=[stock_code],
        start_date=start_date,
        end_date=end_date,
        period="1d",
        dividend_type="front_ratio",
        field_list=["open", "high", "low", "close", "volume"],
        show_progress=False,
    )
    history_frame = _prepare_history_frame(frames.get(stock_code))
    if len(history_frame) < 5:
        raise RuntimeError(f"历史数据不足，无法为 {stock_code} 生成 BBPP 模拟盘配置")

    recent_days = history_frame["trade_date"].tolist()[-5:]
    return {
        "股票代码": stock_code,
        "高价日期": recent_days[-2],
        "低价日期": recent_days[-4],
        "连阳实体开始日期": recent_days[-2],
        "连阳实体结束日期": recent_days[-2],
        "锚定量价节点日期": recent_days[-1],
        "买入方法": buy_method,
        "是否已做": "",
        "买入金额": os.getenv("CYTRADE_BBPP_SMOKETEST_BUY_AMOUNT", "10000"),
        "买入股数": os.getenv("CYTRADE_BBPP_SMOKETEST_BUY_QUANTITY", ""),
    }


def write_runtime_csv(csv_path: Path, row: dict) -> None:
    """把测试行写入独立 CSV。"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "股票代码", "高价日期", "低价日期", "连阳实体开始日期", "连阳实体结束日期",
        "锚定量价节点日期", "买入方法", "是否已做", "买入金额", "买入股数",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)


def build_runtime_settings(runtime_root: Path) -> Settings:
    """构造一份只用于烟雾测试的独立运行配置。"""
    return Settings(
        LOG_DIR=str(runtime_root / "logs"),
        STATE_SAVE_DIR=str(runtime_root / "saved_states"),
        SQLITE_DB_PATH=str(runtime_root / "data" / "db" / "cytrade_smoketest.db"),
        WEB_PORT=int(os.getenv("CYTRADE_BBPP_SMOKETEST_WEB_PORT", "8081")),
    )


def main() -> None:
    """生成测试 CSV 并直接启动 BBPP 模拟盘运行。"""
    stock_code = str(os.getenv("CYTRADE_BBPP_SMOKETEST_CODE", "000001")).strip().zfill(6)
    buy_method = str(os.getenv("CYTRADE_BBPP_SMOKETEST_METHOD", "d")).strip().lower() or "d"
    runtime_root = ROOT / "_runtime_bbpp_smoketest"
    csv_path = runtime_root / "bbpp_signals.csv"

    row = build_smoketest_row(stock_code, buy_method=buy_method)
    write_runtime_csv(csv_path, row)
    os.environ["CYTRADE_BBPP_CSV_PATH"] = str(csv_path)

    settings = build_runtime_settings(runtime_root)
    settings.ensure_dirs()

    print("BBPP 模拟盘测试 CSV 已生成:", csv_path)
    print("测试标的:", stock_code)
    print("买入方法:", buy_method)
    print("Web 端口:", settings.WEB_PORT)
    print("按 Ctrl+C 可退出模拟盘测试")

    run(strategy_classes=[BbppStrategy], settings=settings)


if __name__ == "__main__":
    main()