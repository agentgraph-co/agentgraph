/**
 * Unified control bar for the graph visualization.
 * 2D/3D toggle, zoom, search, entity type filter, cluster filter, layout mode.
 */

interface GraphControlsProps {
  /** Current rendering mode */
  is3D: boolean
  onToggle3D: () => void

  /** Search */
  searchTerm: string
  onSearchChange: (term: string) => void

  /** Entity type filter */
  filterType: 'all' | 'human' | 'agent'
  onFilterTypeChange: (type: 'all' | 'human' | 'agent') => void

  /** Graph mode */
  graphMode: 'full' | 'ego'
  onResetToFull: () => void

  /** Node/edge counts */
  nodeCount: number
  edgeCount: number

  /** Fullscreen toggle */
  isFullscreen: boolean
  onToggleFullscreen: () => void

  /** Side panel toggles */
  onToggleClusters: () => void
  showClusters: boolean
  onToggleStats: () => void
  showStats: boolean
}

export default function GraphControls({
  is3D,
  onToggle3D,
  searchTerm,
  onSearchChange,
  filterType,
  onFilterTypeChange,
  graphMode,
  onResetToFull,
  nodeCount,
  edgeCount,
  isFullscreen,
  onToggleFullscreen,
  onToggleClusters,
  showClusters,
  onToggleStats,
  showStats,
}: GraphControlsProps) {
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      {/* Left side — title + stats */}
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold">Trust Graph</h1>

        {graphMode === 'ego' && (
          <button
            onClick={onResetToFull}
            className="text-xs text-primary-light hover:underline cursor-pointer"
          >
            Back to full graph
          </button>
        )}

        <div className="flex items-center gap-3 text-xs text-text-muted">
          <span>{nodeCount} nodes</span>
          <span>{edgeCount} edges</span>
          {graphMode === 'ego' && (
            <span className="text-primary-light">Ego view</span>
          )}
        </div>
      </div>

      {/* Right side — controls */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Search */}
        <input
          type="search"
          value={searchTerm}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search entities..."
          aria-label="Search graph entities"
          className="bg-surface border border-border rounded-md px-3 py-1.5 text-sm text-text focus:outline-none focus:border-primary w-44"
        />

        {/* Type filter */}
        <div className="flex gap-0.5">
          {(['all', 'human', 'agent'] as const).map((t) => (
            <button
              key={t}
              onClick={() => onFilterTypeChange(t)}
              className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
                filterType === t
                  ? 'bg-primary/10 text-primary-light border border-primary/30'
                  : 'text-text-muted hover:text-text border border-transparent'
              }`}
            >
              {t === 'all' ? 'All' : t === 'human' ? 'Humans' : 'Agents'}
            </button>
          ))}
        </div>

        {/* 2D/3D toggle */}
        <button
          onClick={onToggle3D}
          className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer ${
            is3D
              ? 'bg-accent/10 text-accent border border-accent/30'
              : 'text-text-muted hover:text-text border border-border'
          }`}
        >
          {is3D ? '3D' : '2D'}
        </button>

        {/* Panel toggles */}
        <button
          onClick={onToggleClusters}
          className={`px-2 py-1 rounded text-xs transition-colors cursor-pointer ${
            showClusters
              ? 'bg-primary/10 text-primary-light border border-primary/30'
              : 'text-text-muted hover:text-text border border-transparent'
          }`}
        >
          Clusters
        </button>

        <button
          onClick={onToggleStats}
          className={`px-2 py-1 rounded text-xs transition-colors cursor-pointer ${
            showStats
              ? 'bg-primary/10 text-primary-light border border-primary/30'
              : 'text-text-muted hover:text-text border border-transparent'
          }`}
        >
          Stats
        </button>

        {/* Fullscreen */}
        <button
          onClick={onToggleFullscreen}
          className="px-2.5 py-1 rounded text-xs text-text-muted hover:text-text border border-border hover:border-primary/30 transition-colors cursor-pointer"
        >
          {isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
        </button>
      </div>
    </div>
  )
}
