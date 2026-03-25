<template>
  <el-container style="height:100vh">
    <el-aside width="200px" style="background:#001529">
      <div style="color:white;padding:20px;font-size:18px;font-weight:bold">
        cytrade
      </div>
      <el-menu :router="true" background-color="#001529" text-color="#fff"
               active-text-color="#1890ff" default-active="/">
        <el-menu-item index="/dashboard">📊 总览</el-menu-item>
        <el-menu-item index="/strategies">🤖 策略</el-menu-item>
        <el-menu-item index="/positions">💼 持仓</el-menu-item>
        <el-menu-item index="/orders">📋 订单</el-menu-item>
        <el-menu-item index="/trades">💹 成交</el-menu-item>
      </el-menu>
    </el-aside>
    <el-main>
      <div class="top-status-bar" :class="`top-status-bar--${latencyState.level}`">
        <span class="top-status-badge" :class="`top-status-badge--${latencyState.level}`">
          {{ latencyState.text }}
        </span>
        <span class="top-status-value">{{ latestDataLabel }}</span>
      </div>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useSystemStore } from './stores/system'

const systemStore = useSystemStore()
const { status } = storeToRefs(systemStore)
let ws = null
let heartbeatTimer = null
let reconnectTimer = null
let statusTimer = null
let reconnectAttempts = 0
let isUnmounted = false

function formatDelay(ms) {
  if (!Number.isFinite(ms) || ms <= 0) return '--'
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  return `${Math.round(ms)}ms`
}

function formatDataTime(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const yyyy = date.getFullYear()
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mi = String(date.getMinutes()).padStart(2, '0')
  const ss = String(date.getSeconds()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`
}

const latestDataLabel = computed(() => {
  const latestDataTime = formatDataTime(status.value.latest_data_time)
  const delayText = formatDelay(Number(status.value.data_delay_ms))
  const processText = formatDelay(Number(status.value.strategy_process_total_ms))
  return `最新数据 ${latestDataTime} | 延迟 ${delayText} | 本轮耗时 ${processText}`
})

const latencyState = computed(() => {
  const thresholdSec = Number(status.value.data_latency_threshold_sec || 0)
  const delayMs = Number(status.value.data_delay_ms || 0)
  if (!status.value.trading_time) {
    return { level: 'idle', text: '非交易时段' }
  }
  if (thresholdSec > 0 && delayMs > thresholdSec * 1000) {
    return { level: 'alert', text: '延迟偏高' }
  }
  return { level: 'ok', text: '数据正常' }
})

// 停止心跳定时器，避免页面卸载后继续向服务器发 ping。
function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

// 启动心跳，定时向后端发送 ping，帮助维持连接并探测断线。
function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(() => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send('ping')
    }
  }, 30000)
}

// WebSocket 断开后按指数退避方式重连，避免频繁无意义重试。
function scheduleReconnect() {
  if (isUnmounted || reconnectTimer) return
  const delay = Math.min(3000 * 2 ** reconnectAttempts, 30000)
  reconnectAttempts += 1
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connectWebSocket()
  }, delay)
}

// 建立实时连接，并把后端推送交给 Pinia store 统一处理。
function connectWebSocket() {
  stopHeartbeat()
  if (ws && ws.readyState === WebSocket.OPEN) return

  const wsProtocol = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${wsProtocol}://${location.host}/ws/realtime`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    // 所有实时消息都交给 store 统一分发，页面组件只负责展示。
    systemStore.handleWsMessage(msg)
  }
  ws.onopen = () => {
    reconnectAttempts = 0
    ws.send('ping')
    startHeartbeat()
  }
  ws.onerror = () => ws?.close()
  ws.onclose = () => {
    stopHeartbeat()
    if (!isUnmounted) {
      scheduleReconnect()
    }
  }
}

onMounted(() => {
  // 页面首次挂载时，先拉一次基础状态，再建立实时连接。
  systemStore.fetchStatus()
  statusTimer = setInterval(() => {
    systemStore.fetchStatus()
  }, 5000)
  connectWebSocket()
})

onUnmounted(() => {
  // 页面卸载时彻底清理定时器和连接，避免内存泄漏。
  isUnmounted = true
  stopHeartbeat()
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (statusTimer) clearInterval(statusTimer)
  ws?.close()
})
</script>

<style scoped>
.top-status-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 10px 14px;
  border-radius: 12px;
  background: linear-gradient(135deg, #fff8e1 0%, #ffe8b0 100%);
  border: 1px solid #f0c36d;
}

.top-status-bar--ok {
  background: linear-gradient(135deg, #edfdf3 0%, #d9f7e6 100%);
  border-color: #89d6a7;
}

.top-status-bar--idle {
  background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%);
  border-color: #cbd5e1;
}

.top-status-bar--alert {
  background: linear-gradient(135deg, #fff1f2 0%, #ffe0e5 100%);
  border-color: #f3a6b2;
}

.top-status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.top-status-badge--ok {
  background: #d1fae5;
  color: #065f46;
}

.top-status-badge--idle {
  background: #e5e7eb;
  color: #374151;
}

.top-status-badge--alert {
  background: #ffe4e6;
  color: #be123c;
}

.top-status-value {
  font-size: 13px;
  font-weight: 600;
  color: #5c3b00;
}
</style>
