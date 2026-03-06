"""
历史数据模块
通过 xtdata.download_history_data + xtdata.get_market_data_ex 获取历史行情
"""
import pandas as pd
from typing import Dict, List, Optional
from monitor.logger import get_logger

logger = get_logger("system")

try:
    from xtquant import xtdata
    _XT_AVAILABLE = True
except ImportError:
    _XT_AVAILABLE = False
    xtdata = None  # type: ignore


class HistoryDataManager:
    """历史行情数据获取"""

    # 股票代码转换规则
    _SH_PREFIXES = ("6", "5")   # 上海：6开头（主板）、5开头（ETF）
    _SZ_PREFIXES = ("0", "3")   # 深圳：0开头（主板）、3开头（创业板）

    def get_history_data(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        period: str = "1d",
        dividend_type: str = "front",
    ) -> Dict[str, pd.DataFrame]:
        """
        获取历史行情数据

        Args:
            stock_list:    6位数字股票代码列表
            start_date:    开始日期 'YYYYMMDD'
            end_date:      结束日期 'YYYYMMDD'
            period:        数据周期 1m/5m/15m/30m/60m/1d
            dividend_type: 复权方式 none/front/back

        Returns:
            {stock_code: DataFrame}  （key 为6位代码）
        """
        if not stock_list:
            return {}

        xt_codes = [self.stock_code_to_xt(c) for c in stock_list]

        if not _XT_AVAILABLE:
            logger.warning("HistoryDataManager: xtquant 未安装，返回空数据")
            return {c: pd.DataFrame() for c in stock_list}

        try:
            # 先下载确保本地缓存最新
            for xt_code in xt_codes:
                xtdata.download_history_data(
                    xt_code, period=period,
                    start_time=start_date, end_time=end_date
                )

            raw: dict = xtdata.get_market_data_ex(
                field_list=[],
                stock_list=xt_codes,
                period=period,
                start_time=start_date,
                end_time=end_date,
                dividend_type=dividend_type,
                fill_data=True,
            )

            result: Dict[str, pd.DataFrame] = {}
            for xt_code, df in raw.items():
                code = self.xt_code_to_stock(xt_code)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    result[code] = df
                else:
                    result[code] = pd.DataFrame()

            logger.info(
                "HistoryDataManager: %d 只股票历史数据已获取 (%s~%s %s)",
                len(result), start_date, end_date, period
            )
            return result

        except Exception as e:
            logger.error("HistoryDataManager: 获取数据失败: %s", e, exc_info=True)
            return {c: pd.DataFrame() for c in stock_list}

    @classmethod
    def stock_code_to_xt(cls, code: str) -> str:
        """6位数字代码 → xtquant 格式（含后缀）"""
        code = str(code).strip().zfill(6)
        if code.startswith(cls._SH_PREFIXES):
            return f"{code}.SH"
        return f"{code}.SZ"

    @classmethod
    def xt_code_to_stock(cls, xt_code: str) -> str:
        """xtquant 格式 → 6位数字代码"""
        return xt_code.split(".")[0] if "." in xt_code else xt_code


__all__ = ["HistoryDataManager"]
