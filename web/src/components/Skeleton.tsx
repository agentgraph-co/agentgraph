function Pulse({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-border/50 rounded ${className}`} />
}

export function PostSkeleton() {
  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <div className="flex gap-3">
        <div className="flex flex-col items-center gap-1 pt-1">
          <Pulse className="w-4 h-4" />
          <Pulse className="w-6 h-3" />
          <Pulse className="w-4 h-4" />
        </div>
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <Pulse className="w-24 h-3" />
            <Pulse className="w-12 h-4 rounded-full" />
            <Pulse className="w-16 h-3" />
          </div>
          <Pulse className="w-full h-3" />
          <Pulse className="w-3/4 h-3" />
          <Pulse className="w-1/2 h-3" />
          <div className="flex gap-4 mt-1">
            <Pulse className="w-16 h-3" />
            <Pulse className="w-12 h-3" />
          </div>
        </div>
      </div>
    </div>
  )
}

export function ListingSkeleton() {
  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <div className="flex items-start justify-between mb-2">
        <Pulse className="w-40 h-4" />
        <Pulse className="w-16 h-4" />
      </div>
      <Pulse className="w-full h-3 mb-1" />
      <Pulse className="w-2/3 h-3 mb-3" />
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <Pulse className="w-16 h-5 rounded" />
          <Pulse className="w-20 h-3" />
        </div>
        <Pulse className="w-16 h-3" />
      </div>
    </div>
  )
}

export function ProfileSkeleton() {
  return (
    <div className="bg-surface border border-border rounded-lg p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="space-y-2">
          <Pulse className="w-48 h-7" />
          <div className="flex gap-2">
            <Pulse className="w-14 h-5 rounded" />
            <Pulse className="w-32 h-4" />
          </div>
        </div>
        <Pulse className="w-24 h-8 rounded-md" />
      </div>
      <Pulse className="w-full h-2 rounded-full mb-4" />
      <Pulse className="w-full h-3 mb-1" />
      <Pulse className="w-3/4 h-3 mb-4" />
      <div className="flex gap-6">
        <Pulse className="w-20 h-4" />
        <Pulse className="w-20 h-4" />
        <Pulse className="w-20 h-4" />
      </div>
    </div>
  )
}

export function NotificationSkeleton() {
  return (
    <div className="bg-surface border border-border rounded-lg p-3">
      <div className="flex items-start gap-3">
        <Pulse className="w-6 h-6 rounded" />
        <div className="flex-1 space-y-1.5">
          <div className="flex gap-2">
            <Pulse className="w-32 h-3.5" />
            <Pulse className="w-16 h-3" />
          </div>
          <Pulse className="w-3/4 h-3" />
        </div>
      </div>
    </div>
  )
}

export function AgentCardSkeleton() {
  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <div className="flex items-center gap-3 mb-3">
        <Pulse className="w-10 h-10 rounded-full" />
        <div className="flex-1 space-y-1.5">
          <Pulse className="w-32 h-4" />
          <Pulse className="w-20 h-3" />
        </div>
        <Pulse className="w-16 h-5 rounded" />
      </div>
      <div className="flex gap-2 mb-2">
        <Pulse className="w-14 h-5 rounded-full" />
        <Pulse className="w-18 h-5 rounded-full" />
        <Pulse className="w-12 h-5 rounded-full" />
      </div>
      <Pulse className="w-full h-3" />
    </div>
  )
}

export function WebhookCardSkeleton() {
  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <Pulse className="w-48 h-4" />
        <Pulse className="w-14 h-5 rounded-full" />
      </div>
      <Pulse className="w-full h-3 mb-1" />
      <div className="flex gap-2 mt-2">
        <Pulse className="w-20 h-5 rounded" />
        <Pulse className="w-24 h-5 rounded" />
      </div>
    </div>
  )
}

export function TableRowSkeleton({ cols = 4 }: { cols?: number }) {
  return (
    <tr className="border-b border-border/50">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Pulse className="w-full h-3.5" />
        </td>
      ))}
    </tr>
  )
}
