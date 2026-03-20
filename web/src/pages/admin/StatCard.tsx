export function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <div className="text-2xl font-bold">{typeof value === 'number' ? value.toLocaleString() : value}</div>
      <div className="text-xs text-text-muted mt-1">{label}</div>
      {sub && <div className="text-[10px] text-text-muted/60 mt-0.5">{sub}</div>}
    </div>
  )
}
