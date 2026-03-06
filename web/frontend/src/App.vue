<template>
  <el-container style="height:100vh">
    <el-aside width="200px" style="background:#001529">
      <div style="color:white;padding:20px;font-size:18px;font-weight:bold">
        CyTrade2
      </div>
      <el-menu :router="true" background-color="#001529" text-color="#fff"
               active-text-color="#1890ff" default-active="/">
        <el-menu-item index="/dashboard">📊 总览</el-menu-item>
        <el-menu-item index="/strategies">🤖 策略</el-menu-item>
        <el-menu-item index="/positions">💼 持仓</el-menu-item>
        <el-menu-item index="/orders">📋 订单</el-menu-item>
      </el-menu>
    </el-aside>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useSystemStore } from './stores/system'

const systemStore = useSystemStore()
let ws = null

onMounted(() => {
  systemStore.fetchStatus()
  // WebSocket 连接
  ws = new WebSocket(`ws://${location.host}/ws/realtime`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    systemStore.handleWsMessage(msg)
  }
  ws.onopen = () => ws.send('ping')
  setInterval(() => ws?.readyState === 1 && ws.send('ping'), 30000)
})

onUnmounted(() => ws?.close())
</script>
