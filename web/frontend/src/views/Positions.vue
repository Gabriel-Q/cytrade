<template>
  <div>
    <h2>持仓明细</h2>
    <el-table :data="sortedPositions" stripe>
      <el-table-column type="index" label="序号" width="70" />
      <el-table-column label="标的" min-width="150">
        <template #default="{ row }">
          <div>{{ row.stock_code }}</div>
          <div style="color: var(--el-text-color-secondary); font-size: 12px;">{{ row.stock_name || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="strategy_name" label="策略" />
      <el-table-column label="回转">
        <template #default="scope">{{ scope.row.is_t0 ? 'T+0' : 'T+1' }}</template>
      </el-table-column>
      <el-table-column prop="total_quantity" label="持仓量" />
      <el-table-column prop="available_quantity" label="可用量" />
      <el-table-column prop="avg_cost" label="均价" :formatter="fmt3" />
      <el-table-column prop="current_price" label="现价" :formatter="fmt3" />
      <el-table-column prop="market_value" label="市值" :formatter="fmt0" />
      <el-table-column prop="unrealized_pnl" label="浮动盈亏" :formatter="fmt2" />
      <el-table-column prop="realized_pnl" label="已实现盈亏" :formatter="fmt2" />
      <el-table-column prop="total_buy_commission" label="买佣" :formatter="fmt2" />
      <el-table-column prop="total_sell_commission" label="卖佣" :formatter="fmt2" />
      <el-table-column prop="total_stamp_tax" label="印花税" :formatter="fmt2" />
      <el-table-column prop="total_fees" label="总费用" :formatter="fmt2" />
      <el-table-column label="更新时间" width="190">
        <template #default="{ row }">{{ formatDateTime(row.update_time) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import axios from 'axios'
import { formatDateTime, sortByTimeDesc } from '../utils/table'

const positions = ref([])
const sortedPositions = computed(() =>
  sortByTimeDesc(positions.value, row => row.update_time)
)

async function load() {
  // 定期从后端拉取持仓快照，刷新表格展示。
  const res = await axios.get('/api/positions')
  positions.value = res.data
}
// 不同字段按不同精度格式化，方便展示。
const fmt3 = (_, __, v) => typeof v === 'number' ? v.toFixed(3) : v
const fmt2 = (_, __, v) => typeof v === 'number' ? v.toFixed(2) : v
const fmt0 = (_, __, v) => typeof v === 'number' ? v.toFixed(0) : v
onMounted(() => {
  load(); setInterval(load, 3000)
})
</script>
