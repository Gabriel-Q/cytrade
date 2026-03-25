<template>
  <div>
    <h2>策略管理</h2>
    <div class="toolbar">
      <div class="toolbar-filters">
        <el-radio-group v-model="capacityFilter" size="small">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="waiting">只看排队中</el-radio-button>
          <el-radio-button label="occupying">只看占用名额</el-radio-button>
        </el-radio-group>
        <el-select v-model="strategyTypeFilter" size="small" style="width: 180px" placeholder="全部策略类型">
          <el-option label="全部策略类型" value="all" />
          <el-option
            v-for="strategyType in strategyTypes"
            :key="strategyType"
            :label="strategyType"
            :value="strategyType"
          />
        </el-select>
      </div>
      <div class="toolbar-summary">
        共 {{ strategies.length }} 个实例，当前显示 {{ sortedStrategies.length }} 个
      </div>
    </div>

    <el-table :data="sortedStrategies" stripe :row-class-name="strategyRowClassName">
      <el-table-column type="index" label="序号" width="70" />
      <el-table-column prop="strategy_name" label="策略" />
      <el-table-column label="标的" min-width="150">
        <template #default="{ row }">
          <div>{{ row.stock_code }}</div>
          <div style="color: var(--el-text-color-secondary); font-size: 12px;">{{ row.stock_name || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态">
        <template #default="{ row }">
          <div class="status-cell">
            <el-tag :type="tagType(row.status)">{{ row.status_text || statusText(row.status) }}</el-tag>
            <el-tag v-if="isWaitingForCapacity(row)" type="warning" effect="dark" class="capacity-tag">
              BBPP 等待空余名额
            </el-tag>
            <div v-else-if="row.pause_reason" class="pause-reason-text">{{ row.pause_reason }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="名额管理" width="180">
        <template #default="{ row }">
          <div class="capacity-cell">
            <el-tag :type="row.capacity?.enabled ? 'primary' : 'info'" size="small">
              {{ row.capacity?.enabled ? '已启用' : '未启用' }}
            </el-tag>
            <template v-if="row.capacity?.enabled">
              <div class="capacity-metrics">{{ row.capacity.used }}/{{ row.capacity.limit }} 已占用</div>
              <div v-if="row.capacity.waiting" class="capacity-meta capacity-meta-wait">当前实例排队中</div>
              <div v-else-if="row.capacity.occupying" class="capacity-meta capacity-meta-active">当前实例占用名额</div>
              <div v-else class="capacity-meta">剩余 {{ row.capacity.remaining }}</div>
            </template>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="190">
        <template #default="{ row }">{{ formatDateTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column prop="total_quantity" label="持仓量" />
      <el-table-column prop="avg_cost" label="均价" :formatter="fmt2" />
      <el-table-column prop="unrealized_pnl" label="浮动盈亏" :formatter="fmt2" />
      <el-table-column label="操作" width="320">
        <template #default="{ row }">
          <el-button size="small" @click="pause(row)">暂停</el-button>
          <el-button size="small" type="primary" @click="resume(row)">恢复</el-button>
          <el-button size="small" type="danger" @click="close(row)">平仓</el-button>
          <el-button
            v-if="showRuntimeStateButton(row)"
            size="small"
            :type="runtimeStateButtonType(row)"
            @click="clearRuntimeState(row)"
          >
            清运行态
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { strategyStatusText, strategyStatusTagType } from '../utils/status'
import { formatDateTime, sortByTimeDesc } from '../utils/table'

const strategies = ref([])
const capacityFilter = ref('all')
const strategyTypeFilter = ref('all')

const strategyTypes = computed(() => {
  return Array.from(new Set(
    strategies.value
      .map(row => String(row?.strategy_type || '').trim())
      .filter(Boolean)
  )).sort((left, right) => left.localeCompare(right, 'zh-CN'))
})

const filteredStrategies = computed(() => {
  let rows = strategies.value
  if (strategyTypeFilter.value !== 'all') {
    rows = rows.filter(row => String(row?.strategy_type || '') === strategyTypeFilter.value)
  }
  if (capacityFilter.value === 'waiting') {
    return rows.filter(row => Boolean(row?.capacity?.waiting))
  }
  if (capacityFilter.value === 'occupying') {
    return rows.filter(row => Boolean(row?.capacity?.occupying))
  }
  return rows
})

const sortedStrategies = computed(() =>
  sortByTimeDesc(filteredStrategies.value, row => row.create_time)
)

async function load() {
  // 拉取当前所有策略的最新状态。
  const res = await axios.get('/api/strategies')
  strategies.value = res.data
}

function isWaitingForCapacity(row) {
  return Boolean(row?.capacity?.waiting) || String(row?.pause_reason || '').includes('等待空余名额')
}

function strategyRowClassName({ row }) {
  return isWaitingForCapacity(row) ? 'capacity-wait-row' : ''
}

function showRuntimeStateButton(row) {
  return ['PAUSED', 'ERROR'].includes(String(row?.status || '').toUpperCase())
}

function runtimeStateButtonType(row) {
  return String(row?.status || '').toUpperCase() === 'ERROR' ? 'danger' : 'warning'
}

async function pause(row) {
  // 调用后端接口暂停策略，然后重新刷新列表。
  await axios.post(`/api/strategies/${row.strategy_id}/pause`)
  ElMessage.success('已暂停')
  load()
}

async function resume(row) {
  // 调用后端接口恢复策略，然后重新刷新列表。
  await axios.post(`/api/strategies/${row.strategy_id}/resume`)
  ElMessage.success('已恢复')
  load()
}

async function close(row) {
  // 平仓属于风险较高操作，先弹确认框，避免误点。
  const stockLabel = row.stock_name ? `${row.stock_code} ${row.stock_name}` : row.stock_code
  await ElMessageBox.confirm(`确认对 ${stockLabel} 执行强制平仓？`, '确认', { type: 'warning' })
  await axios.post(`/api/strategies/${row.strategy_id}/close`)
  ElMessage.success('平仓指令已发送')
  load()
}

async function clearRuntimeState(row) {
  const stockLabel = row.stock_name ? `${row.stock_code} ${row.stock_name}` : row.stock_code
  await ElMessageBox.confirm(
    `确认清空 ${stockLabel} 的运行态快照？此操作不会删除订单、成交和持仓历史。`,
    '确认',
    { type: 'warning' }
  )
  const res = await axios.post(`/api/strategies/${row.strategy_id}/clear-runtime-state`)
  ElMessage.success(res?.data?.message || '已清空运行态')
  load()
}

// 页面内统一的数字格式化函数。
const fmt2 = (_, __, val) => typeof val === 'number' ? val.toFixed(2) : val
const statusText = strategyStatusText
const tagType = strategyStatusTagType

onMounted(() => {
  load(); setInterval(load, 5000)
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.toolbar-summary {
  color: #6b7280;
  font-size: 13px;
  font-weight: 600;
}

.toolbar-filters {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.status-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.capacity-tag {
  width: fit-content;
  font-weight: 700;
}

.pause-reason-text {
  color: #b45309;
  font-size: 12px;
  font-weight: 600;
}

.capacity-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.capacity-metrics {
  color: #1f2937;
  font-size: 12px;
  font-weight: 700;
}

.capacity-meta {
  color: #6b7280;
  font-size: 12px;
}

.capacity-meta-active {
  color: #047857;
  font-weight: 600;
}

.capacity-meta-wait {
  color: #b45309;
  font-weight: 700;
}

:deep(.capacity-wait-row) {
  --el-table-tr-bg-color: #fff7e6;
}

:deep(.capacity-wait-row td) {
  box-shadow: inset 0 1px 0 #f5d38a, inset 0 -1px 0 #f5d38a;
}
</style>
