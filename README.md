# CyTrade2

CyTrade2 是一个基于 [xtquant](https://dict.thinktrader.net/nativeApi/start_now.html) / QMT 的 Python 量化交易框架，覆盖以下完整链路：

- 交易连接与自动重连
- 实时行情订阅与分发
- 策略运行与状态恢复
- 订单追踪与成交回调
- 持仓管理与盈亏统计
- Watchdog 监控告警
- FastAPI + Vue Web 控制台

当前仓库适合以下用途：

- 作为个人量化交易框架骨架
- 作为 xtquant/QMT 集成示例
- 作为策略开发、回放验证、Web 控台集成的学习项目

> 安全说明：仓库默认不再包含任何真实账号、密码、令牌或本地客户端路径。运行前请自行配置本地环境。

---

## 特性

| 模块 | 能力 |
|---|---|
| 连接管理 | QMT 连接、断线重连、重连回调 |
| 数据订阅 | 个股订阅、全市场订阅、重连后恢复订阅 |
| 交易执行 | 限价、市价、按金额下单、平仓、撤单 |
| 订单管理 | UUID 追踪、柜台单号映射、成交/状态更新 |
| 持仓管理 | 移动平均成本、FIFO、实时浮盈/实盈统计 |
| 策略框架 | `BaseStrategy`、信号与交易分离、风控前置 |
| 策略运行 | 选股、行情分发、调度、快照恢复、停止归档 |
| 数据持久化 | SQLite、本地状态恢复、可选 PostgreSQL 同步 |
| 监控告警 | 心跳、连接状态、数据超时、CPU/内存、钉钉通知 |
| Web 控制台 | FastAPI REST、WebSocket、Vue 3 前端 |

---

## 项目结构

```text
cytrade2/
├── config/                  # 枚举、配置
├── core/                    # QMT 回调、连接、订阅、历史数据
├── data/                    # SQLite / 状态文件 / 可选远程同步
├── monitor/                 # 日志、看门狗
├── position/                # 持仓模型与管理器
├── strategy/                # 策略基类、运行器、示例策略
├── trading/                 # 交易执行、订单管理、交易模型
├── web/                     # FastAPI 后端 + Vue 前端
├── tests/                   # pytest 回归测试
├── main.py                  # 主入口
├── requirements.txt
├── 设计文档.md
├── plan.md
└── 终审.md
```

---

## 运行环境

- Python 3.10 推荐
- Windows
- 已安装并可登录的 QMT 客户端
- Node.js 18+（仅前端开发时需要）

Python 依赖见 `requirements.txt`，前端依赖见 `web/frontend/package.json`。

---

## 快速开始

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

如后续已发布到 PyPI，也可直接安装：

```bash
pip install cytrade2
```

### 2. 配置本地环境

框架支持两种配置方式：

1. 直接修改 `config/settings.py`
2. 通过环境变量覆盖默认值（推荐开源使用方式）

常用环境变量如下：

| 变量名 | 说明 | 示例 |
|---|---|---|
| `QMT_PATH` | QMT 客户端路径 | `D:\QMT\XtMiniQmt.exe` |
| `ACCOUNT_ID` | 资金账号 | `your_account_id` |
| `ACCOUNT_PASSWORD` | 登录密码 | `your_password` |
| `SQLITE_DB_PATH` | SQLite 路径 | `./data/db/cytrade2.db` |
| `STATE_SAVE_DIR` | 策略状态目录 | `./saved_states` |
| `LOG_DIR` | 日志目录 | `./logs` |
| `WEB_PORT` | Web 端口 | `8080` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `ENABLE_REMOTE_DB` | 是否启用远程同步 | `false` |

参考环境变量模板见 `.env.example`。

### 3. 启动主程序

```bash
python main.py
```

默认会加载示例策略 `TestGridStrategy`。

启动后默认可访问：

- REST API: `http://localhost:8080/api`
- WebSocket: `ws://localhost:8080/ws/realtime`

### 4. 启动前端（可选）

```bash
cd web/frontend
npm install
npm run dev
```

---

## 核心设计

### 交易主链路

```text
xtquant/QMT
  -> callback.py
  -> order_manager.py / connection.py
  -> position/manager.py
  -> strategy/runner.py
  -> strategy/base.py
  -> trading/executor.py
```

### 设计原则

- 策略只产出信号，不直接操作底层接口
- 订单、成交、持仓分层处理
- 回调统一做异常保护
- 重连后自动恢复订阅
- 清仓后自动归档策略盈亏
- Web 撤单走真实交易执行链路

---

## 开发策略

在 `strategy/` 下新增策略文件，并继承 `BaseStrategy`。

最小示例如下：

```python
from strategy.base import BaseStrategy
from strategy.models import StrategyConfig
from core.models import TickData


class MyStrategy(BaseStrategy):
    strategy_name = "MyStrategy"

    def select_stocks(self) -> list[StrategyConfig]:
        return [
            StrategyConfig(
                stock_code="000001",
                entry_price=10.0,
                stop_loss_price=9.5,
                take_profit_price=11.0,
                max_position_amount=50_000,
            )
        ]

    def on_tick(self, tick: TickData) -> dict | None:
        if tick.last_price <= self.config.entry_price:
            return {
                "action": "BUY",
                "price": tick.last_price,
                "amount": 10_000,
                "remark": "entry signal",
            }
        return None
```

然后在 `main.py` 中注册：

```python
from strategy.my_strategy import MyStrategy

run(strategy_classes=[MyStrategy])
```

参考实现：`strategy/test_grid_strategy.py`

---

## Web 接口概览

后端提供常用控制与监控接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/strategies` | 查询策略 |
| POST | `/api/strategies/{id}/pause` | 暂停策略 |
| POST | `/api/strategies/{id}/resume` | 恢复策略 |
| POST | `/api/strategies/{id}/close` | 强制平仓 |
| GET | `/api/positions` | 查询持仓 |
| GET | `/api/orders` | 查询订单 |
| POST | `/api/orders/{uuid}/cancel` | 撤单 |
| GET | `/api/trades` | 查询成交 |
| GET | `/api/system/status` | 系统状态 |
| GET | `/api/system/logs` | 最近日志 |

前端技术栈：

- Vue 3
- Vite
- Element Plus
- Pinia

---

## 测试

当前基线：`50 passed`

```bash
python -m pytest tests/ -v
```

当前已覆盖：

- 连接管理
- 数据管理
- 数据订阅恢复
- 主入口装配
- 订单管理
- 交易执行
- 持仓计算
- 策略运行
- Web 撤单链路

说明：策略状态持久化当前采用 `pickle`，用于项目内部跨交易日恢复；
不保证跨大版本结构变更后的兼容性。

---

## 打包与发布

本项目已支持标准 Python 打包。

### 本地构建

```bash
python -m build
python -m twine check dist/*
```

### 发布到 PyPI

推荐通过环境变量提供凭据：

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=<your-pypi-token>
python -m twine upload dist/*
```

Windows PowerShell 可用：

```powershell
$env:TWINE_USERNAME="__token__"
$env:TWINE_PASSWORD="<your-pypi-token>"
python -m twine upload dist/*
```

本地示例配置见 `.pypirc.example`，但不要提交真实 `.pypirc`。

---

## 开源使用建议

### 1. 不要提交真实配置

请勿把以下信息提交到仓库：

- QMT 客户端真实路径
- 资金账号和密码
- 钉钉 Webhook / Secret
- 数据库账号密码
- 任意 Git / API Token

### 2. 建议本地忽略的内容

项目已附带 `.gitignore`，建议本地运行文件、日志、数据库、状态文件都不要纳入版本控制。

### 3. 当前已知限制

- 强依赖 Windows + QMT 环境
- `xtquant` 不同版本的订阅参数细节可能存在差异
- 状态恢复基于 `pickle`，更适合内部运行态恢复，不适合作为长期兼容存档格式

---

## 相关文档

- `设计文档.md`：总体设计说明
- `plan.md`：详细实施计划
- `整改追踪表.md`：问题与整改跟踪
- `终审.md`：终审结论与修复回写
- `CONTRIBUTING.md`：贡献约定
- `SECURITY.md`：安全说明
- `RELEASE_CHECKLIST.md`：发布前检查清单
- `CHANGELOG.md`：版本变更记录

---

## 免责声明

本项目仅用于学习、研究和自有环境验证，不构成任何投资建议。  
实盘使用前，请自行完成：

- 账户权限核验
- 行情与交易接口版本核验
- 风控规则核验
- 长时间稳定性测试
- 真实环境回归测试

---

## License

本项目采用 [MIT License](LICENSE)。
2. **日期格式**：统一使用 `"YYYYMMDD"` 字符串（如 `"20260227"`）。
3. **Mock 模式**：未连接 QMT 时，`TradeExecutor` 自动进入 Mock 模式，订单在内存中模拟成交，适用于策略逻辑调试。
4. **跨交易日恢复**：每日 15:05 定时保存策略快照到 `saved_states/`；下次启动时自动加载当天状态文件。
5. **最小下单单位**：`buy_by_amount` 按 100 股取整，不足 100 股时不下单。
