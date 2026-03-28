// ─── Discovery Card ───
// Renders a single discovered source from cross-registry discovery.
// Used in BotOnboarding preview step.

import SourceBadge from './SourceBadge'

interface DiscoveredSource {
  provider: string
  identifier: string
  source_url: string
  discovery_method: string
  community_signals: Record<string, number>
}

interface DiscoveryCardProps {
  source: DiscoveredSource
  selected: boolean
  onToggle: (provider: string) => void
}

export default function DiscoveryCard({ source, selected, onToggle }: DiscoveryCardProps) {
  return (
    <label
      className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
        selected
          ? 'border-primary/50 bg-primary/5'
          : 'border-border bg-surface hover:bg-surface-hover'
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(source.provider)}
        className="accent-primary w-4 h-4 shrink-0"
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <SourceBadge
            sourceUrl={source.source_url}
            sourceType={source.provider}
            communitySignals={source.community_signals}
            compact
          />
        </div>
        <p className="text-[10px] text-text-muted truncate">
          via {source.discovery_method}
        </p>
      </div>
    </label>
  )
}

interface DiscoveryResultsProps {
  sources: DiscoveredSource[]
  selected: Set<string>
  onToggle: (provider: string) => void
}

export function DiscoveryResults({ sources, selected, onToggle }: DiscoveryResultsProps) {
  if (sources.length === 0) return null

  return (
    <div className="mt-4">
      <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
        Discovered across {sources.length} {sources.length === 1 ? 'registry' : 'registries'}
      </h4>
      <div className="grid gap-2">
        {sources.map((source) => (
          <DiscoveryCard
            key={source.provider}
            source={source}
            selected={selected.has(source.provider)}
            onToggle={onToggle}
          />
        ))}
      </div>
    </div>
  )
}
