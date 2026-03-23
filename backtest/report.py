"""回测报告生成器。

第一阶段目标不是做复杂 BI，而是把：
1. 回测参数
2. 基础指标
3. 净值曲线
4. 订单/成交明细

输出成一份可直接打开的 HTML 报告。
"""

from __future__ import annotations

import json
from pathlib import Path

from backtest.models import BacktestResult


class BacktestReportBuilder:
    """HTML 报告生成器。"""

    _METRIC_GROUPS = {
        "收益指标": [
            "starting_equity",
            "ending_equity",
            "total_return",
            "annualized_return",
            "total_realized_pnl",
            "avg_daily_return",
            "best_day_return",
            "worst_day_return",
        ],
        "风险指标": [
            "max_drawdown",
            "sharpe",
            "daily_win_rate",
            "trading_days",
        ],
        "交易指标": [
            "trade_count",
            "order_count",
            "closed_trade_count",
            "winning_trade_count",
            "losing_trade_count",
            "win_rate",
            "avg_win_pnl",
            "avg_loss_pnl",
            "profit_loss_ratio",
            "profit_factor",
            "total_fee",
        ],
    }

    _METRIC_LABELS = {
        "starting_equity": "初始净值",
        "ending_equity": "期末净值",
        "total_return": "总收益率",
        "annualized_return": "年化收益率",
        "total_realized_pnl": "已实现盈亏",
        "avg_daily_return": "平均逐日收益",
        "best_day_return": "最佳单日收益",
        "worst_day_return": "最差单日收益",
        "max_drawdown": "最大回撤",
        "sharpe": "夏普比率",
        "daily_win_rate": "按日胜率",
        "trading_days": "交易日数",
        "trade_count": "成交笔数",
        "order_count": "订单记录数",
        "closed_trade_count": "闭合交易数",
        "winning_trade_count": "盈利交易数",
        "losing_trade_count": "亏损交易数",
        "win_rate": "胜率",
        "avg_win_pnl": "平均盈利",
        "avg_loss_pnl": "平均亏损",
        "profit_loss_ratio": "盈亏比",
        "profit_factor": "Profit Factor",
        "total_fee": "总费用",
    }

    def build_html(self, result: BacktestResult) -> str:
        """把回测结果转成 HTML 文本。"""
        metrics_tables = self._build_metric_tables(result.metrics)
        equity_points = [
            {
                "time": point.data_time.isoformat(),
                "equity": point.equity,
                "drawdown": point.drawdown,
            }
            for point in result.equity_curve
        ]
        daily_return_points = [
            {
                "trade_day": item.trade_day,
                "equity": item.equity,
                "daily_return": item.daily_return,
            }
            for item in result.daily_returns
        ]
        order_rows = "".join(
            "<tr>"
            f"<td>{item.get('create_time', '')}</td>"
            f"<td>{item.get('strategy_name', '')}</td>"
            f"<td>{item.get('stock_code', '')}</td>"
            f"<td>{item.get('direction', '')}</td>"
            f"<td>{item.get('status', '')}</td>"
            f"<td>{item.get('price', 0)}</td>"
            f"<td>{item.get('quantity', 0)}</td>"
            "</tr>"
            for item in result.orders[-200:]
        )
        trade_rows = "".join(
            "<tr>"
            f"<td>{item.get('trade_time', '')}</td>"
            f"<td>{item.get('strategy_name', '')}</td>"
            f"<td>{item.get('stock_code', '')}</td>"
            f"<td>{item.get('direction', '')}</td>"
            f"<td>{item.get('price', 0)}</td>"
            f"<td>{item.get('quantity', 0)}</td>"
            f"<td>{item.get('total_fee', 0)}</td>"
            "</tr>"
            for item in result.trades[-200:]
        )
        daily_return_rows = "".join(
            "<tr>"
            f"<td>{item.trade_day}</td>"
            f"<td>{item.equity:.2f}</td>"
            f"<td>{item.daily_return:.6f}</td>"
            "</tr>"
            for item in result.daily_returns[-60:]
        )
        closed_trade_rows = "".join(
            "<tr>"
            f"<td>{item.entry_time.isoformat()}</td>"
            f"<td>{item.exit_time.isoformat()}</td>"
            f"<td>{item.strategy_name}</td>"
            f"<td>{item.stock_code}</td>"
            f"<td>{item.quantity}</td>"
            f"<td>{item.entry_price:.4f}</td>"
            f"<td>{item.exit_price:.4f}</td>"
            f"<td>{item.pnl:.4f}</td>"
            f"<td>{item.return_ratio:.6f}</td>"
            f"<td>{item.holding_days:.2f}</td>"
            "</tr>"
            for item in result.closed_trades[-200:]
        )
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <title>回测报告</title>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <style>
        body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #1f2937; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
        th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; font-size: 14px; }}
        th {{ background: #f3f4f6; text-align: left; }}
        .chart {{ width: 100%; height: 420px; margin-bottom: 24px; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
        .metric-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-bottom: 24px; }}
        .metric-card h3 {{ margin: 0 0 12px; }}
    </style>
</head>
<body>
    <h1>回测报告</h1>
    <h2>参数</h2>
    <table>
        <tr><th>股票列表</th><td>{', '.join(result.config.stock_codes)}</td></tr>
        <tr><th>开始日期</th><td>{result.config.start_date}</td></tr>
        <tr><th>结束日期</th><td>{result.config.end_date}</td></tr>
        <tr><th>周期</th><td>{result.config.period}</td></tr>
        <tr><th>初始资金</th><td>{result.config.initial_cash:.2f}</td></tr>
        <tr><th>滑点</th><td>{result.config.slippage:.4f}</td></tr>
    </table>
    <h2>指标</h2>
    <div class="metric-grid">{metrics_tables}</div>
    <div class="grid">
        <div id="equity" class="chart"></div>
        <div id="drawdown" class="chart"></div>
        <div id="daily-return" class="chart"></div>
        <div id="return-distribution" class="chart"></div>
    </div>
    <h2>最近订单</h2>
    <table>
        <thead><tr><th>时间</th><th>策略</th><th>股票</th><th>方向</th><th>状态</th><th>价格</th><th>数量</th></tr></thead>
        <tbody>{order_rows}</tbody>
    </table>
    <h2>最近成交</h2>
    <table>
        <thead><tr><th>时间</th><th>策略</th><th>股票</th><th>方向</th><th>价格</th><th>数量</th><th>费用</th></tr></thead>
        <tbody>{trade_rows}</tbody>
    </table>
    <h2>逐日收益</h2>
    <table>
        <thead><tr><th>交易日</th><th>日末净值</th><th>逐日收益</th></tr></thead>
        <tbody>{daily_return_rows}</tbody>
    </table>
    <h2>闭合交易明细</h2>
    <table>
        <thead><tr><th>开仓时间</th><th>平仓时间</th><th>策略</th><th>股票</th><th>数量</th><th>开仓价</th><th>平仓价</th><th>盈亏</th><th>收益率</th><th>持有天数</th></tr></thead>
        <tbody>{closed_trade_rows}</tbody>
    </table>
    <script>
        const equityPoints = {json.dumps(equity_points, ensure_ascii=False)};
        const dailyReturns = {json.dumps(daily_return_points, ensure_ascii=False)};
        Plotly.newPlot('equity', [{{
            x: equityPoints.map(item => item.time),
            y: equityPoints.map(item => item.equity),
            type: 'scatter',
            mode: 'lines',
            name: '净值'
        }}], {{ title: '净值曲线' }});
        Plotly.newPlot('drawdown', [{{
            x: equityPoints.map(item => item.time),
            y: equityPoints.map(item => item.drawdown),
            type: 'scatter',
            mode: 'lines',
            name: '回撤'
        }}], {{ title: '回撤曲线' }});
        Plotly.newPlot('daily-return', [{{
            x: dailyReturns.map(item => item.trade_day),
            y: dailyReturns.map(item => item.daily_return),
            type: 'bar',
            name: '逐日收益'
        }}], {{ title: '逐日收益曲线' }});
        Plotly.newPlot('return-distribution', [{{
            x: dailyReturns.slice(1).map(item => item.daily_return),
            type: 'histogram',
            name: '日收益分布'
        }}], {{ title: '日收益分布' }});
    </script>
</body>
</html>"""

    def _build_metric_tables(self, metrics: dict) -> str:
        """按收益/风险/交易分组生成指标表。"""
        cards = []
        for title, keys in self._METRIC_GROUPS.items():
            rows = "".join(
                f"<tr><th>{self._METRIC_LABELS.get(key, key)}</th><td>{self._format_metric_value(metrics.get(key))}</td></tr>"
                for key in keys
                if key in metrics
            )
            cards.append(f'<div class="metric-card"><h3>{title}</h3><table>{rows}</table></div>')
        return "".join(cards)

    @staticmethod
    def _format_metric_value(value) -> str:
        """统一格式化数值指标，便于报表阅读。"""
        if isinstance(value, float):
            return f"{value:.6f}"
        if isinstance(value, int):
            return str(value)
        return "" if value is None else str(value)

    def write(self, result: BacktestResult, output_path: str | Path) -> Path:
        """把回测报告写入文件。"""
        path = Path(output_path)
        path.write_text(self.build_html(result), encoding="utf-8")
        return path
