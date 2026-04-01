export function CardSkeleton() {
  return (
    <div className="bg-bg-card border border-border-col rounded-card p-4">
      <div className="skeleton w-12 h-12 rounded-full mb-3" />
      <div className="skeleton h-4 w-3/4 mb-2" />
      <div className="skeleton h-3 w-1/2" />
    </div>
  )
}

export function ListSkeleton({ rows = 5 }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-3 bg-bg-card rounded-card">
          <div className="skeleton w-10 h-10 rounded-full shrink-0" />
          <div className="flex-1">
            <div className="skeleton h-4 w-1/2 mb-2" />
            <div className="skeleton h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function PageSkeleton() {
  return (
    <div className="p-8 space-y-6 animate-pulse">
      <div className="skeleton h-10 w-1/3" />
      <div className="skeleton h-5 w-1/2" />
      <div className="grid grid-cols-4 gap-4 mt-8">
        {[...Array(4)].map((_, i) => <div key={i} className="skeleton h-24 rounded-card" />)}
      </div>
    </div>
  )
}
