export function formatNumber(n) {
  if (!n && n !== 0) return '—'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

export function formatMs(ms) {
  if (!ms) return '—'
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return `${m}:${String(s).padStart(2, '0')}`
}

// Deterministic color from string
export function hashColor(str) {
  const PALETTE = [
    '#1db954','#e91e8c','#ff6b35','#00d4ff',
    '#a855f7','#f59e0b','#10b981','#ef4444',
    '#3b82f6','#ec4899','#84cc16','#f97316',
  ]
  let hash = 0
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash)
  return PALETTE[Math.abs(hash) % PALETTE.length]
}

export function slugify(str) {
  return str.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '')
}
