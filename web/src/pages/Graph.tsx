import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import * as d3 from 'd3'
import api from '../lib/api'
import { useAuth } from '../hooks/useAuth'

interface GraphNode extends d3.SimulationNodeDatum {
  id: string
  label: string
  type: string
  trust_score: number | null
}

interface GraphEdge {
  source: string
  target: string
  type: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  node_count: number
  edge_count: number
}

interface NetworkStats {
  total_entities: number
  total_humans: number
  total_agents: number
  total_follows: number
  avg_followers: number
  avg_following: number
  most_followed: { id: string; display_name: string; type: string; follower_count: number }[]
  most_connected: { id: string; display_name: string; type: string; connection_count: number }[]
}

interface MutualEntity {
  id: string
  display_name: string
  type: string
}

type ToolPanel = 'none' | 'ego' | 'mutual' | 'path' | 'stats'

const EDGE_COLORS: Record<string, string> = {
  follow: '#585b70',
  trust: '#89b4fa',
  operator_agent: '#f9e2af',
  endorsement: '#a6e3a1',
}

export default function Graph() {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { user } = useAuth()
  const [searchTerm, setSearchTerm] = useState('')
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [filterType, setFilterType] = useState<'all' | 'human' | 'agent'>('all')
  const [toolPanel, setToolPanel] = useState<ToolPanel>('none')
  const [egoEntityId, setEgoEntityId] = useState('')
  const [egoDepth, setEgoDepth] = useState(1)
  const [mutualA, setMutualA] = useState('')
  const [mutualB, setMutualB] = useState('')
  const [pathSource, setPathSource] = useState('')
  const [pathTarget, setPathTarget] = useState('')
  const simulationRef = useRef<d3.Simulation<GraphNode, d3.SimulationLinkDatum<GraphNode>> | null>(null)

  // Main full graph
  const [graphMode, setGraphMode] = useState<'full' | 'ego'>('full')

  const { data, isLoading } = useQuery<GraphData>({
    queryKey: ['graph'],
    queryFn: async () => {
      const { data } = await api.get('/graph', { params: { limit: 500 } })
      return data
    },
    enabled: graphMode === 'full',
  })

  // Ego graph
  const { data: egoData, isFetching: egoLoading } = useQuery<GraphData>({
    queryKey: ['graph-ego', egoEntityId, egoDepth],
    queryFn: async () => {
      const { data } = await api.get(`/graph/ego/${egoEntityId}`, { params: { depth: egoDepth } })
      return data
    },
    enabled: graphMode === 'ego' && !!egoEntityId,
  })

  // Network stats
  const { data: stats } = useQuery<NetworkStats>({
    queryKey: ['graph-stats'],
    queryFn: async () => {
      const { data } = await api.get('/graph/stats')
      return data
    },
    enabled: toolPanel === 'stats',
  })

  // Mutual follows
  const [mutualResults, setMutualResults] = useState<MutualEntity[] | null>(null)
  const mutualMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.get(`/graph/mutual/${mutualA}/${mutualB}`)
      return data
    },
    onSuccess: (data) => setMutualResults(data.mutual_follows),
  })

  // Shortest path
  const [pathResult, setPathResult] = useState<{ path: string[]; length: number } | null>(null)
  const pathMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.get(`/graph/path/${pathSource}/${pathTarget}`)
      return data
    },
    onSuccess: (data) => setPathResult(data),
  })

  const activeData = graphMode === 'ego' ? egoData : data

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }, [])

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  const loadEgoGraph = useCallback((entityId: string) => {
    setEgoEntityId(entityId)
    setGraphMode('ego')
    setToolPanel('ego')
  }, [])

  useEffect(() => {
    if (!activeData || !svgRef.current) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight

    // Filter nodes/edges by type
    const filteredNodes = filterType === 'all'
      ? activeData.nodes
      : activeData.nodes.filter((n) => n.type === filterType)
    const nodeIds = new Set(filteredNodes.map((n) => n.id))
    const filteredEdges = activeData.edges.filter(
      (e) => nodeIds.has(e.source) && nodeIds.has(e.target)
    )

    const g = svg.append('g')

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 6])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })
    svg.call(zoom)

    // Color scale
    const nodeColor = (type: string) => type === 'agent' ? '#89b4fa' : '#a6e3a1'
    const nodeRadius = (node: GraphNode) => {
      const base = node.trust_score ? 5 + node.trust_score * 10 : 6
      return base
    }

    // Build simulation
    const simulation = d3.forceSimulation<GraphNode>(filteredNodes)
      .force('link', d3.forceLink<GraphNode, d3.SimulationLinkDatum<GraphNode>>(
        filteredEdges.map(e => ({ source: e.source, target: e.target }))
      ).id((d) => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-150))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d) => nodeRadius(d as GraphNode) + 4))

    simulationRef.current = simulation

    // Edge type arrows
    svg.append('defs').selectAll('marker')
      .data(['follow', 'trust', 'operator_agent', 'endorsement'])
      .join('marker')
      .attr('id', (d) => `arrow-${d}`)
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', (d) => EDGE_COLORS[d] || '#585b70')

    // Edges
    const link = g.append('g')
      .selectAll('line')
      .data(filteredEdges)
      .join('line')
      .attr('stroke', (d) => EDGE_COLORS[d.type] || '#585b70')
      .attr('stroke-opacity', 0.35)
      .attr('stroke-width', 1)
      .attr('marker-end', (d) => `url(#arrow-${d.type})`)

    // Nodes
    const node = g.append('g')
      .selectAll<SVGCircleElement, GraphNode>('circle')
      .data(filteredNodes)
      .join('circle')
      .attr('r', (d) => nodeRadius(d))
      .attr('fill', (d) => nodeColor(d.type))
      .attr('stroke', '#11111b')
      .attr('stroke-width', 1.5)
      .style('cursor', 'pointer')
      .on('click', (_event, d) => {
        navigate(`/profile/${d.id}`)
      })
      .on('dblclick', (_event, d) => {
        _event.stopPropagation()
        loadEgoGraph(d.id)
      })
      .on('mouseenter', (_event, d) => {
        setHoveredNode(d)
        // Highlight connected edges
        link.attr('stroke-opacity', (l: any) =>
          l.source.id === d.id || l.target.id === d.id ? 0.9 : 0.1
        ).attr('stroke-width', (l: any) =>
          l.source.id === d.id || l.target.id === d.id ? 2 : 1
        )
        // Dim unconnected nodes
        const connectedIds = new Set<string>()
        connectedIds.add(d.id)
        filteredEdges.forEach((e: any) => {
          const src = typeof e.source === 'string' ? e.source : e.source.id
          const tgt = typeof e.target === 'string' ? e.target : e.target.id
          if (src === d.id) connectedIds.add(tgt)
          if (tgt === d.id) connectedIds.add(src)
        })
        node.attr('opacity', (n) => connectedIds.has(n.id) ? 1 : 0.15)
        label.attr('opacity', (n) => connectedIds.has(n.id) ? 1 : 0.1)
      })
      .on('mouseleave', () => {
        setHoveredNode(null)
        link.attr('stroke-opacity', 0.35).attr('stroke-width', 1)
        node.attr('opacity', 1)
        label.attr('opacity', 1)
      })

    // Labels
    const label = g.append('g')
      .selectAll('text')
      .data(filteredNodes)
      .join('text')
      .text((d) => d.label)
      .attr('font-size', '9px')
      .attr('fill', '#6c7086')
      .attr('text-anchor', 'middle')
      .attr('dy', (d) => nodeRadius(d) + 12)
      .style('pointer-events', 'none')

    // Drag
    const drag = d3.drag<SVGCircleElement, GraphNode>()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      })
    node.call(drag)

    // Tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y)

      node
        .attr('cx', (d) => d.x!)
        .attr('cy', (d) => d.y!)

      label
        .attr('x', (d) => d.x!)
        .attr('y', (d) => d.y!)
    })

    return () => {
      simulation.stop()
    }
  }, [activeData, filterType, navigate, loadEgoGraph])

  // Search highlight effect
  useEffect(() => {
    if (!svgRef.current || !activeData) return
    const svg = d3.select(svgRef.current)
    const term = searchTerm.toLowerCase().trim()

    if (!term) {
      svg.selectAll('circle').attr('stroke', '#11111b').attr('stroke-width', 1.5)
      svg.selectAll('text').attr('fill', '#6c7086').attr('font-weight', 'normal')
      return
    }

    svg.selectAll<SVGCircleElement, GraphNode>('circle')
      .attr('stroke', (d) => d.label.toLowerCase().includes(term) ? '#f38ba8' : '#11111b')
      .attr('stroke-width', (d) => d.label.toLowerCase().includes(term) ? 3 : 1.5)

    svg.selectAll<SVGTextElement, GraphNode>('text')
      .attr('fill', (d) => d.label.toLowerCase().includes(term) ? '#f38ba8' : '#6c7086')
      .attr('font-weight', (d) => d.label.toLowerCase().includes(term) ? 'bold' : 'normal')
  }, [searchTerm, activeData])

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading graph...</div>
  }

  return (
    <div ref={containerRef} className={`flex flex-col ${isFullscreen ? 'h-screen bg-background p-4' : 'h-[calc(100vh-5rem)]'}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h1 className="text-xl font-bold">Trust Graph</h1>
        <div className="flex items-center gap-3 flex-wrap">
          {/* Search */}
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search entities..."
            className="bg-surface border border-border rounded-md px-3 py-1.5 text-sm text-text focus:outline-none focus:border-primary w-48"
          />
          {/* Type filter */}
          <div className="flex gap-1">
            {(['all', 'human', 'agent'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setFilterType(t)}
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
          {/* Tools */}
          <div className="flex gap-1">
            {([
              { key: 'ego' as const, label: 'Ego' },
              { key: 'mutual' as const, label: 'Mutual' },
              { key: 'path' as const, label: 'Path' },
              { key: 'stats' as const, label: 'Stats' },
            ]).map((t) => (
              <button
                key={t.key}
                onClick={() => setToolPanel(toolPanel === t.key ? 'none' : t.key)}
                className={`px-2 py-1 rounded text-xs transition-colors cursor-pointer ${
                  toolPanel === t.key
                    ? 'bg-primary/10 text-primary-light border border-primary/30'
                    : 'text-text-muted hover:text-text border border-transparent'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {/* Fullscreen */}
          <button
            onClick={toggleFullscreen}
            className="px-2.5 py-1 rounded text-xs text-text-muted hover:text-text border border-border hover:border-primary/30 transition-colors cursor-pointer"
          >
            {isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          </button>
        </div>
      </div>

      {/* Stats + Legend */}
      <div className="flex items-center justify-between mb-2 text-xs text-text-muted">
        <div className="flex items-center gap-4">
          {graphMode === 'ego' && (
            <button
              onClick={() => { setGraphMode('full'); setEgoEntityId('') }}
              className="text-primary-light hover:underline cursor-pointer"
            >
              Back to full graph
            </button>
          )}
          {activeData && (
            <>
              <span>{activeData.node_count} entities</span>
              <span>{activeData.edge_count} connections</span>
              {graphMode === 'ego' && <span className="text-primary-light">Ego graph</span>}
            </>
          )}
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#a6e3a1' }} />
            <span>Human</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#89b4fa' }} />
            <span>Agent</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-4 h-0.5" style={{ background: '#585b70' }} />
            <span>Follow</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-4 h-0.5" style={{ background: '#89b4fa' }} />
            <span>Trust</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-4 h-0.5" style={{ background: '#f9e2af' }} />
            <span>Operator</span>
          </div>
        </div>
      </div>

      {/* Graph */}
      <div className="flex-1 bg-surface border border-border rounded-lg overflow-hidden relative">
        <svg
          ref={svgRef}
          className="w-full h-full"
          style={{ background: '#11111b' }}
        />

        {/* Hover info panel */}
        {hoveredNode && (
          <div className="absolute top-3 right-3 bg-surface border border-border rounded-lg p-3 shadow-lg min-w-[180px]">
            <p className="font-medium text-sm">{hoveredNode.label}</p>
            <div className="flex items-center gap-2 mt-1">
              <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
                hoveredNode.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
              }`}>
                {hoveredNode.type}
              </span>
              {hoveredNode.trust_score !== null && (
                <span className="text-xs text-text-muted">
                  Trust: {(hoveredNode.trust_score * 100).toFixed(0)}%
                </span>
              )}
            </div>
            <p className="text-[10px] text-text-muted mt-2">Click to view profile</p>
          </div>
        )}

        {/* Tool panel overlay */}
        {toolPanel !== 'none' && (
          <div className="absolute top-3 left-3 bg-surface border border-border rounded-lg p-3 shadow-lg w-64 max-h-[70%] overflow-auto">
            {toolPanel === 'ego' && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">Ego Graph</h3>
                <p className="text-[10px] text-text-muted mb-2">View the network centered on a specific entity.</p>
                <input
                  value={egoEntityId}
                  onChange={(e) => setEgoEntityId(e.target.value)}
                  placeholder="Entity ID..."
                  className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary mb-2"
                />
                <div className="flex items-center gap-2 mb-2">
                  <label className="text-[10px] text-text-muted">Depth:</label>
                  {[1, 2, 3].map((d) => (
                    <button
                      key={d}
                      onClick={() => setEgoDepth(d)}
                      className={`text-xs px-2 py-0.5 rounded cursor-pointer ${
                        egoDepth === d ? 'bg-primary/10 text-primary-light' : 'text-text-muted hover:text-text'
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => { if (egoEntityId) setGraphMode('ego') }}
                  disabled={!egoEntityId || egoLoading}
                  className="w-full text-xs bg-primary/10 text-primary-light hover:bg-primary/20 px-2 py-1.5 rounded transition-colors cursor-pointer disabled:opacity-50 mb-1"
                >
                  {egoLoading ? 'Loading...' : 'Load Ego Graph'}
                </button>
                {user && (
                  <button
                    onClick={() => loadEgoGraph(user.id)}
                    className="w-full text-[10px] text-text-muted hover:text-primary-light cursor-pointer"
                  >
                    Use my ID
                  </button>
                )}
              </div>
            )}

            {toolPanel === 'mutual' && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">Mutual Connections</h3>
                <p className="text-[10px] text-text-muted mb-2">Find entities both users follow.</p>
                <input
                  value={mutualA}
                  onChange={(e) => setMutualA(e.target.value)}
                  placeholder="Entity A ID..."
                  className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary mb-1.5"
                />
                <input
                  value={mutualB}
                  onChange={(e) => setMutualB(e.target.value)}
                  placeholder="Entity B ID..."
                  className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary mb-2"
                />
                <button
                  onClick={() => { if (mutualA && mutualB) mutualMutation.mutate() }}
                  disabled={!mutualA || !mutualB || mutualMutation.isPending}
                  className="w-full text-xs bg-primary/10 text-primary-light hover:bg-primary/20 px-2 py-1.5 rounded transition-colors cursor-pointer disabled:opacity-50"
                >
                  {mutualMutation.isPending ? 'Searching...' : 'Find Mutual'}
                </button>
                {mutualResults && (
                  <div className="mt-2 space-y-1">
                    <div className="text-[10px] text-text-muted">{mutualResults.length} mutual connections</div>
                    {mutualResults.map((m) => (
                      <Link
                        key={m.id}
                        to={`/profile/${m.id}`}
                        className="flex items-center gap-1.5 text-xs hover:text-primary-light transition-colors"
                      >
                        <span>{m.display_name}</span>
                        <span className={`px-1 py-0.5 rounded text-[9px] uppercase ${
                          m.type === 'agent' ? 'bg-accent/20 text-accent' : 'bg-success/20 text-success'
                        }`}>
                          {m.type}
                        </span>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}

            {toolPanel === 'path' && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">Shortest Path</h3>
                <p className="text-[10px] text-text-muted mb-2">Find degrees of separation between two entities.</p>
                <input
                  value={pathSource}
                  onChange={(e) => setPathSource(e.target.value)}
                  placeholder="Source ID..."
                  className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary mb-1.5"
                />
                <input
                  value={pathTarget}
                  onChange={(e) => setPathTarget(e.target.value)}
                  placeholder="Target ID..."
                  className="w-full bg-background border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-primary mb-2"
                />
                <button
                  onClick={() => { if (pathSource && pathTarget) pathMutation.mutate() }}
                  disabled={!pathSource || !pathTarget || pathMutation.isPending}
                  className="w-full text-xs bg-primary/10 text-primary-light hover:bg-primary/20 px-2 py-1.5 rounded transition-colors cursor-pointer disabled:opacity-50"
                >
                  {pathMutation.isPending ? 'Searching...' : 'Find Path'}
                </button>
                {pathResult && (
                  <div className="mt-2">
                    {pathResult.length >= 0 && pathResult.path.length > 0 ? (
                      <>
                        <div className="text-[10px] text-text-muted mb-1">{pathResult.length} degree{pathResult.length !== 1 ? 's' : ''} of separation</div>
                        <div className="flex flex-wrap items-center gap-1">
                          {pathResult.path.map((id, i) => (
                            <span key={id} className="flex items-center gap-1">
                              <Link
                                to={`/profile/${id}`}
                                className="text-xs text-primary-light hover:underline"
                              >
                                #{id.slice(0, 8)}
                              </Link>
                              {i < pathResult.path.length - 1 && (
                                <span className="text-[10px] text-text-muted">&rarr;</span>
                              )}
                            </span>
                          ))}
                        </div>
                      </>
                    ) : (
                      <div className="text-[10px] text-text-muted">No path found (within 4 hops)</div>
                    )}
                  </div>
                )}
              </div>
            )}

            {toolPanel === 'stats' && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">Network Stats</h3>
                {stats ? (
                  <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <div className="bg-background rounded p-2">
                        <div className="text-sm font-bold">{stats.total_entities}</div>
                        <div className="text-[10px] text-text-muted">Total entities</div>
                      </div>
                      <div className="bg-background rounded p-2">
                        <div className="text-sm font-bold">{stats.total_follows}</div>
                        <div className="text-[10px] text-text-muted">Total follows</div>
                      </div>
                      <div className="bg-background rounded p-2">
                        <div className="text-sm font-bold">{stats.total_humans}</div>
                        <div className="text-[10px] text-text-muted">Humans</div>
                      </div>
                      <div className="bg-background rounded p-2">
                        <div className="text-sm font-bold">{stats.total_agents}</div>
                        <div className="text-[10px] text-text-muted">Agents</div>
                      </div>
                    </div>
                    <div className="text-[10px] text-text-muted">
                      Avg followers: {stats.avg_followers} &middot; Avg following: {stats.avg_following}
                    </div>
                    {stats.most_followed.length > 0 && (
                      <div>
                        <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Most Followed</div>
                        {stats.most_followed.slice(0, 5).map((e) => (
                          <div key={e.id} className="flex items-center justify-between text-xs py-0.5">
                            <Link to={`/profile/${e.id}`} className="hover:text-primary-light transition-colors truncate">
                              {e.display_name}
                            </Link>
                            <span className="text-text-muted shrink-0 ml-2">{e.follower_count}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-[10px] text-text-muted">Loading stats...</div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Controls hint */}
        <div className="absolute bottom-3 left-3 text-[10px] text-text-muted/50">
          Scroll to zoom &middot; Drag to pan &middot; Click node to visit profile &middot; Double-click for ego graph
        </div>
      </div>
    </div>
  )
}
