<template>
  <div>
    <h2>系统总览</h2>
    <el-row :gutter="16">
      <el-col :span="6">
        <el-card>
          <div class="metric">
            <div class="label">连接状态</div>
            <div :style="{color: status.connected?'green':'red', fontSize:'20px'}">
              {{ status.connected ? '已连接' : '断开' }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="metric">
            <div class="label">运行策略</div>
            <div style="font-size:28px;font-weight:bold">{{ status.strategy_count }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="metric">
            <div class="label">活跃订单</div>
            <div style="font-size:28px;font-weight:bold">{{ status.active_orders }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="metric">
            <div class="label">CPU / 内存</div>
            <div>{{ status.cpu_pct?.toFixed(1) }}% / {{ status.mem_pct?.toFixed(1) }}%</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="6">
        <el-card>
          <div class="metric">
            <div class="label">持仓市值</div>
            <div class="number">{{ fmt2(positionSummary.total_market_value) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="metric">
            <div class="label">总盈亏</div>
            <div class="number" :style="pnlStyle(positionSummary.total_pnl)">
              {{ fmt2(positionSummary.total_pnl) }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="metric">
            <div class="label">累计总费用</div>
            <div class="number">{{ fmt2(positionSummary.total_fees) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="metric">
            <div class="label">持仓标的数</div>
            <div class="number">{{ positionSummary.positions_count }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top: 16px;">
      <template #header>
        <span>费用统计</span>
      </template>
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="metric">
            <div class="label">买入佣金</div>
            <div class="sub-number">{{ fmt2(positionSummary.total_buy_commission) }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric">
            <div class="label">卖出佣金</div>
            <div class="sub-number">{{ fmt2(positionSummary.total_sell_commission) }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric">
            <div class="label">印花税</div>
            <div class="sub-number">{{ fmt2(positionSummary.total_stamp_tax) }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric">
            <div class="label">已实现盈亏</div>
            <div class="sub-number" :style="pnlStyle(positionSummary.total_realized_pnl)">
              {{ fmt2(positionSummary.total_realized_pnl) }}
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card style="margin-top: 16px;">
      <template #header>
        <span>策略容量概览</span>
      </template>
      <el-table :data="capacitySummary" stripe empty-text="当前没有启用容量限制的策略">
        <el-table-column prop="strategy_type" label="策略类型" min-width="160" />
        <el-table-column prop="instance_count" label="实例数" width="90" />
        <el-table-column label="名额使用" width="120">
          <template #default="{ row }">{{ row.used }}/{{ row.limit }}</template>
        </el-table-column>
        <el-table-column prop="occupying_count" label="占用中" width="90" />
        <el-table-column prop="waiting_count" label="排队中" width="90" />
        <el-table-column prop="remaining" label="剩余" width="90" />
        <el-table-column label="等待标的" min-width="260">
          <template #default="{ row }">
            <div v-if="row.waiting_items.length" class="capacity-chip-wrap">
              <div v-for="item in row.waiting_items" :key="item.strategy_id" class="capacity-chip">
                <div class="capacity-chip-code">{{ item.stock_code }}</div>
                <div class="capacity-chip-name">{{ item.stock_name || item.strategy_name }}</div>
              </div>
            </div>
            <div v-else class="capacity-empty-inline">-</div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useSystemStore } from '../stores/system'

const store = useSystemStore()
const { status, positionSummary, capacitySummary } = storeToRefs(store)
let timer = null

function refresh() {
  // 首页展示的是摘要数据，因此同时刷新系统状态和持仓汇总。
  store.fetchStatus()
  store.fetchPositionSummary()
  store.fetchCapacitySummary()
}

function fmt2(value) {
  // 统一把金额和盈亏格式化成两位小数，避免模板里写重复逻辑。
  return typeof value === 'number' ? value.toFixed(2) : value
}

function pnlStyle(value) {
  // A 股常见习惯：盈利红色，亏损绿色。
  if (typeof value !== 'number') return {}
  if (value > 0) return { color: '#f56c6c' }
  if (value < 0) return { color: '#67c23a' }
  return {}
}

onMounted(() => {
  // 首次进入页面时立即刷新一次，之后再定时轮询。
  refresh()
  timer = setInterval(refresh, 5000)
})

onUnmounted(() => {
  // 页面销毁时记得清理定时器。
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.metric { text-align: center; padding: 10px 0; }
.label { color: #999; margin-bottom: 8px; }
.number { font-size: 24px; font-weight: bold; }
.sub-number { font-size: 20px; font-weight: bold; }
.capacity-wait-text { color: #b45309; }
.capacity-list { margin-top: 18px; }
.capacity-list-title { font-size: 14px; font-weight: 700; margin-bottom: 10px; color: #1f2937; }
.capacity-chip-wrap { display: flex; flex-wrap: wrap; gap: 10px; }
.capacity-chip {
  min-width: 140px;
  padding: 10px 12px;
  border-radius: 12px;
  background: linear-gradient(135deg, #fff7e6 0%, #fde7b1 100%);
  border: 1px solid #f2cc7d;
}
.capacity-chip-code { font-size: 13px; font-weight: 800; color: #92400e; }
.capacity-chip-name { margin-top: 4px; font-size: 12px; color: #7c5a10; }
.capacity-empty { margin-top: 16px; color: #6b7280; font-size: 13px; }
.capacity-empty-inline { color: #9ca3af; font-size: 13px; }
</style>
