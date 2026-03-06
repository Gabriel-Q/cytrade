import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useSystemStore = defineStore('system', () => {
  const status = ref({ connected: false, trading_time: false,
                        strategy_count: 0, active_orders: 0,
                        cpu_pct: 0, mem_pct: 0 })
  const realtimeTicks = ref({})

  async function fetchStatus() {
    try {
      const res = await axios.get('/api/system/status')
      status.value = res.data
    } catch (e) { console.error(e) }
  }

  function handleWsMessage(msg) {
    if (msg.type === 'tick') {
      realtimeTicks.value[msg.code] = msg
    }
  }

  return { status, realtimeTicks, fetchStatus, handleWsMessage }
})
