import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

interface ScoreTimelinePoint {
  recorded_at: string
  score: number
}

interface FrameworkScanItem {
  framework: string
  scan_result: string
  scanned_at: string
  vulnerabilities_count: number
}

interface ScanHistoryResponse {
  repo: string
  entity_id: string | null
  score_timeline: ScoreTimelinePoint[]
  framework_scans: FrameworkScanItem[]
}

const publicApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 15_000,
})

interface Props {
  owner: string
  repo: string
}

function resultColor(scanResult: string): { bg: string; text: string; ring: string } {
  const r = (scanResult || '').toLowerCase()
  if (r === 'clean') {
    return {
      bg: 'bg-emerald-500/10',
      text: 'text-emerald-400',
      ring: 'ring-emerald-500/30',
    }
  }
  if (r === 'warnings' || r === 'warning') {
    return {
      bg: 'bg-amber-500/10',
      text: 'text-amber-400',
      ring: 'ring-amber-500/30',
    }
  }
  if (r === 'critical' || r === 'error') {
    return {
      bg: 'bg-red-500/10',
      text: 'text-red-400',
      ring: 'ring-red-500/30',
    }
  }
  return {
    bg: 'bg-surface-2',
    text: 'text-text-muted',
    ring: 'ring-border',
  }
}

function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

function ScoreSparkline({ points }: { points: ScoreTimelinePoint[] }) {
  if (points.length === 0) return null

  const width = 600
  const height = 140
  const padX = 24
  const padY = 16
  const innerW = width - padX * 2
  const innerH = height - padY * 2

  const xs = points.map((_p, i) =>
    points.length === 1 ? padX + innerW / 2 : padX + (i / (points.length - 1)) * innerW
  )
  const minScore = Math.max(0, Math.min(...points.map(p => p.score)) - 5)
  const maxScore = Math.min(100, Math.max(...points.map(p => p.score)) + 5)
  const range = Math.max(1, maxScore - minScore)
  const ys = points.map(p => padY + innerH - ((p.score - minScore) / range) * innerH)

  const path = points
    .map((_p, i) => `${i === 0 ? 'M' : 'L'}${xs[i].toFixed(1)},${ys[i].toFixed(1)}`)
    .join(' ')

  const lastPoint = points[points.length - 1]
  const lastColor =
    lastPoint.score >= 81 ? '#2DD4BF' : lastPoint.score >= 41 ? '#F59E0B' : '#EF4444'

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-32"
        role="img"
        aria-label="Trust score over time"
      >
        <line
          x1={padX}
          y1={height - padY}
          x2={width - padX}
          y2={height - padY}
          stroke="currentColor"
          strokeOpacity="0.15"
          strokeWidth="1"
        />
        <path
          d={path}
          fill="none"
          stroke={lastColor}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {xs.map((x, i) => (
          <circle
            key={i}
            cx={x}
            cy={ys[i]}
            r={i === xs.length - 1 ? 4 : 2.5}
            fill={lastColor}
            fillOpacity={i === xs.length - 1 ? 1 : 0.6}
          />
        ))}
      </svg>
      <div className="flex justify-between text-[10px] text-text-muted mt-1 px-1">
        <span>{formatDate(points[0].recorded_at)}</span>
        {points.length > 1 && (
          <span className="font-mono">
            {points[0].score} &rarr; {lastPoint.score}
          </span>
        )}
        <span>{formatDate(lastPoint.recorded_at)}</span>
      </div>
    </div>
  )
}

export default function ScanHistoryPanel({ owner, repo }: Props) {
  const { data, isLoading, isError } = useQuery<ScanHistoryResponse>({
    queryKey: ['public-scan-history', owner, repo],
    queryFn: async () => {
      const { data } = await publicApi.get(`/public/scan/${owner}/${repo}/history`)
      return data
    },
    staleTime: 5 * 60_000,
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="bg-surface border border-border rounded-xl p-4">
        <div className="h-4 w-32 bg-surface-2 rounded animate-pulse mb-4" />
        <div className="h-32 bg-surface-2 rounded animate-pulse" />
      </div>
    )
  }

  if (isError || !data) return null

  const hasTimeline = data.score_timeline.length > 0
  const hasScans = data.framework_scans.length > 0

  return (
    <div className="bg-surface border border-border rounded-xl p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-primary">Scan History</h2>
        <span className="text-[10px] uppercase tracking-wider text-text-muted">
          living record
        </span>
      </div>

      {!hasTimeline && !hasScans ? (
        <div className="text-center py-6 text-sm text-text-muted">
          <p>No history yet — this is the first scan.</p>
          <p className="text-xs mt-1">
            Bookmark this page; it&rsquo;ll fill in as scans run.
          </p>
        </div>
      ) : (
        <>
          {hasTimeline && (
            <div>
              <p className="text-xs text-text-muted mb-2">
                Trust score over time ({data.score_timeline.length}{' '}
                {data.score_timeline.length === 1 ? 'sample' : 'samples'})
              </p>
              <ScoreSparkline points={data.score_timeline} />
            </div>
          )}

          {hasScans && (
            <div>
              <p className="text-xs text-text-muted mb-2">
                Framework scans ({data.framework_scans.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {data.framework_scans.map((scan, i) => {
                  const c = resultColor(scan.scan_result)
                  return (
                    <div
                      key={`${scan.framework}-${scan.scanned_at}-${i}`}
                      className={`flex items-center gap-2 ${c.bg} ${c.text} ring-1 ${c.ring} rounded-lg px-2.5 py-1.5 text-xs`}
                    >
                      <span className="font-mono uppercase">{scan.framework}</span>
                      <span className="opacity-60">&middot;</span>
                      <span className="capitalize">{scan.scan_result}</span>
                      {scan.vulnerabilities_count > 0 && (
                        <>
                          <span className="opacity-60">&middot;</span>
                          <span>
                            {scan.vulnerabilities_count}{' '}
                            {scan.vulnerabilities_count === 1 ? 'issue' : 'issues'}
                          </span>
                        </>
                      )}
                      <span className="opacity-60">&middot;</span>
                      <span className="text-[10px] opacity-80">
                        {formatDate(scan.scanned_at)}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
