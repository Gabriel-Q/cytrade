<template>
  <div>
    <h2>订单记录</h2>
    <el-table :data="sortedOrders" stripe height="600">
      <el-table-column type="index" label="序号" width="70" />
      <el-table-column label="标的" min-width="150">
        <template #default="{ row }">
          <div>{{ row.stock_code }}</div>
          <div style="color: var(--el-text-color-secondary); font-size: 12px;">{{ row.stock_name || row.instrument_name || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="direction" label="方向" width="70">
        <template #default="{ row }">
          {{ row.direction_text || directionText(row.direction) }}
        </template>
      </el-table-column>
      <el-table-column prop="order_type" label="类型" width="90">
        <template #default="{ row }">
          {{ row.order_type_text || typeText(row.order_type) }}
        </template>
      </el-table-column>
      <el-table-column label="委托价" width="90">
        <template #default="{ row }">
          {{ displayOrderPrice(row) }}
        </template>
      </el-table-column>
      <el-table-column prop="quantity" label="委托量" width="80" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <div class="status-cell">
            <el-tag :type="tagType(row.status)" size="small">{{ row.status_text || statusText(row.status) }}</el-tag>
            <div v-if="statusHint(row)" class="status-hint">{{ statusHint(row) }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="filled_quantity" label="成交量" width="80" />
      <el-table-column prop="filled_avg_price" label="成交均价" width="90" :formatter="fmt3" />
      <el-table-column prop="remark" label="备注" />
      <el-table-column width="260">
        <template #header>
          <div class="time-header">
            <span>时间</span>
            <el-tooltip
              content="本地提交时间优先看 submitted_at；create_time 为兼容字段；xt raw 为 Xt 原始 order_time 的格式化展示。"
              placement="top"
            >
              <span class="time-help">?</span>
            </el-tooltip>
          </div>
        </template>
        <template #default="{ row }">
          <div class="time-cell">
            <div>
              <span class="time-label">本地提交</span>
              <span>{{ formatDateTime(row.submitted_at) }}</span>
            </div>
            <div>
              <span class="time-label">兼容创建</span>
              <span>{{ formatDateTime(row.create_time) }}</span>
            </div>
            <div>
              <span class="time-label">Xt 原始</span>
              <span>{{ formatDateTime(row.order_time) }}</span>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button v-if="canCancelOrder(row)" size="small" type="danger" plain @click="cancelOrder(row)">
            撤单
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
import {
  orderStatusText,
  orderStatusTagType,
  orderDirectionText,
  orderTypeText,
} from '../utils/status'
import { formatDateTime, sortByTimeDesc, toTimeValue } from '../utils/table'

const orders = ref([])
const sortedOrders = computed(() =>
  sortByTimeDesc(orders.value, row => row.submitted_at, row => row.create_time, row => row.order_time, row => row.update_time)
)

function canCancelOrder(row) {
  return Boolean(row?.cancellable)
}

function waitReportingHint(row) {
  if (String(row?.status || '').toUpperCase() !== 'WAIT_REPORTING') {
    return ''
  }
  return '已提交，待柜台回报'
}

function statusHint(row) {
  const statusMsg = String(row?.status_msg || '').trim()
  if (statusMsg) {
    return statusMsg
  }
  if (String(row?.status || '').toUpperCase() === 'WAIT_REPORTING' && !row?.cancellable) {
    return '历史待报记录，当前不可撤'
  }
  return waitReportingHint(row)
}

async function load() {
  // 订单页采用简单轮询，定期从后端取最新订单状态。
  const res = await axios.get('/api/orders')
  orders.value = res.data
}

async function cancelOrder(row) {
  const stockLabel = row.stock_name ? `${row.stock_code} ${row.stock_name}` : row.stock_code
  await ElMessageBox.confirm(`确认撤销 ${stockLabel} 的未完成订单？`, '确认', { type: 'warning' })
  const res = await axios.post(`/api/orders/${row.order_uuid}/cancel`)
  if (res?.data?.success) {
    ElMessage.success(res.data.message || '撤单请求已发送')
  } else {
    ElMessage.warning(res?.data?.message || '撤单请求未成功')
  }
  await load()
}
// 统一把价格按三位小数展示，更适合股票价格阅读。
const fmt3 = (_, __, v) => typeof v === 'number' ? v.toFixed(3) : v

function displayOrderPrice(row) {
  const text = String(row?.display_price_text || '').trim()
  if (text) {
    return text
  }
  if (String(row?.order_type || '').toUpperCase() === 'MARKET') {
    return '最新价'
  }
  return fmt3(null, null, row?.submitted_price ?? row?.price)
}

const directionText = orderDirectionText
const typeText = orderTypeText
const statusText = orderStatusText
const tagType = orderStatusTagType
onMounted(() => {
  // 进入页面先加载一次，再每 3 秒刷新一次。
  load(); setInterval(load, 3000)
})
</script>

<style scoped>
.status-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.status-hint {
  color: #6b7280;
  font-size: 12px;
  line-height: 1.2;
}

.time-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  line-height: 1.3;
}

.time-header {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.time-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 1px solid #d1d5db;
  border-radius: 999px;
  color: #6b7280;
  font-size: 11px;
  line-height: 1;
  cursor: help;
}

.time-label {
  display: inline-block;
  min-width: 64px;
  color: #6b7280;
}
</style>
