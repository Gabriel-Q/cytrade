function parseDigitTime(text) {
  const digits = String(text || '').replace(/\D/g, '')
  if (!digits) return 0

  if (digits.length === 13) {
    const value = Number(digits)
    return Number.isFinite(value) ? value : 0
  }

  if (digits.length === 10) {
    const value = Number(digits)
    return Number.isFinite(value) ? value * 1000 : 0
  }

  if (digits.length >= 14) {
    const year = digits.slice(0, 4)
    const month = digits.slice(4, 6)
    const day = digits.slice(6, 8)
    const hour = digits.slice(8, 10)
    const minute = digits.slice(10, 12)
    const second = digits.slice(12, 14)
    const parsed = Date.parse(`${year}-${month}-${day}T${hour}:${minute}:${second}`)
    return Number.isNaN(parsed) ? 0 : parsed
  }

  if (digits.length >= 8) {
    const year = digits.slice(0, 4)
    const month = digits.slice(4, 6)
    const day = digits.slice(6, 8)
    const parsed = Date.parse(`${year}-${month}-${day}T00:00:00`)
    return Number.isNaN(parsed) ? 0 : parsed
  }

  return 0
}

export function toTimeValue(value) {
  if (value == null || value === '') return 0

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 0
    const digits = String(Math.trunc(Math.abs(value)))
    if (digits.length === 14 || digits.length === 8) {
      return parseDigitTime(digits)
    }
    if (value > 1e12) return value
    if (value > 1e9) return value * 1000
    return value
  }

  const text = String(value).trim()
  if (!text) return 0

  const direct = Date.parse(text.replace(' ', 'T'))
  if (!Number.isNaN(direct)) {
    return direct
  }

  return parseDigitTime(text)
}

function pad2(value) {
  return String(value).padStart(2, '0')
}

export function formatDateTime(value) {
  const timeValue = toTimeValue(value)
  if (timeValue > 0) {
    const date = new Date(timeValue)
    if (!Number.isNaN(date.getTime())) {
      return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
    }
  }

  const digits = String(value || '').replace(/\D/g, '')
  if (digits.length >= 14) {
    return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)} ${digits.slice(8, 10)}:${digits.slice(10, 12)}:${digits.slice(12, 14)}`
  }
  if (digits.length >= 8) {
    return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)} 00:00:00`
  }
  return value ? String(value).replace('T', ' ').slice(0, 19) : '-'
}

export function sortByTimeDesc(items, ...selectors) {
  const normalized = Array.isArray(items) ? items.slice() : []
  return normalized.sort((left, right) => {
    for (const selector of selectors) {
      const rightTime = toTimeValue(selector(right))
      const leftTime = toTimeValue(selector(left))
      if (rightTime !== leftTime) {
        return rightTime - leftTime
      }
    }
    return 0
  })
}