import { motion } from 'framer-motion'

export default function AudioFeatureBar({ featureName, value, color = '#1db954' }) {
  const pct = Math.round((value ?? 0) * 100)

  return (
    <div className="flex items-center gap-3 py-1">
      <span className="text-xs text-text-secondary w-24 capitalize shrink-0">{featureName}</span>
      <div className="flex-1 h-1.5 bg-bg-hover rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ background: color }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
        />
      </div>
      <span className="text-xs font-mono text-text-muted w-8 text-right shrink-0">
        {value != null ? value.toFixed(2) : '—'}
      </span>
    </div>
  )
}
