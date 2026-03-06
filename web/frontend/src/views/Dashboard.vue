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
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useSystemStore } from '../stores/system'

const store = useSystemStore()
const { status } = storeToRefs(store)

onMounted(() => {
  store.fetchStatus()
  setInterval(store.fetchStatus, 5000)
})
</script>

<style scoped>
.metric { text-align: center; padding: 10px 0; }
.label { color: #999; margin-bottom: 8px; }
</style>
