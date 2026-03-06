<template>
  <div>
    <h2>订单记录</h2>
    <el-table :data="orders" stripe height="600">
      <el-table-column prop="stock_code" label="标的" width="80" />
      <el-table-column prop="direction" label="方向" width="70" />
      <el-table-column prop="order_type" label="类型" width="90" />
      <el-table-column prop="price" label="委托价" width="80" :formatter="fmt3" />
      <el-table-column prop="quantity" label="委托量" width="80" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="tagType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="filled_quantity" label="成交量" width="80" />
      <el-table-column prop="filled_avg_price" label="成交均价" width="90" :formatter="fmt3" />
      <el-table-column prop="remark" label="备注" />
      <el-table-column prop="create_time" label="时间" width="160" />
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const orders = ref([])
async function load() {
  const res = await axios.get('/api/orders')
  orders.value = res.data
}
const fmt3 = (_, __, v) => typeof v === 'number' ? v.toFixed(3) : v
const tagType = s => ({
  FILLED: 'success', PARTIALLY_FILLED: 'warning',
  CANCELLED: 'info', FAILED: 'danger', SUBMITTED: ''
}[s] || '')
onMounted(() => { load(); setInterval(load, 3000) })
</script>
