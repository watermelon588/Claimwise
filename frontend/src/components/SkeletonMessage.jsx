// Placeholder lines paired with Pip while the first reply token is pending.

/** Skeleton reply row. */
export default function SkeletonMessage() {
  return (
    <div className="space-y-2.5 pt-2.5" aria-hidden="true">
      <div className="animate-shimmer h-3 w-11/12 rounded-full" />
      <div className="animate-shimmer h-3 w-4/5 rounded-full" />
      <div className="animate-shimmer h-3 w-3/5 rounded-full" />
    </div>
  )
}
