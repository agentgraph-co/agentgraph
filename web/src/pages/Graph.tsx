import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import * as d3 from 'd3'
import api from '../lib/api'

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
  const [searchTerm, setSearchTerm] = useState('')
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [filterType, setFilterType] = useState<'all' | 'human' | 'agent'>('all')
  const simulationRef = useRef<d3.Simulation<GraphNode, d3.SimulationLinkDatum<GraphNode>> | null>(null)

  const { data, isLoading } = useQuery<GraphData>({
    queryKey: ['graph'],
    queryFn: async () => {
      const { data } = await api.get('/graph', { params: { limit: 500 } })
      return data
    },
  })

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

  useEffect(() => {
    if (!data || !svgRef.current) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight

    // Filter nodes/edges by type
    const filteredNodes = filterType === 'all'
      ? data.nodes
      : data.nodes.filter((n) => n.type === filterType)
    const nodeIds = new Set(filteredNodes.map((n) => n.id))
    const filteredEdges = data.edges.filter(
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
  }, [data, filterType, navigate])

  // Search highlight effect
  useEffect(() => {
    if (!svgRef.current || !data) return
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
  }, [searchTerm, data])

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
          {data && (
            <>
              <span>{data.node_count} entities</span>
              <span>{data.edge_count} connections</span>
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

        {/* Controls hint */}
        <div className="absolute bottom-3 left-3 text-[10px] text-text-muted/50">
          Scroll to zoom &middot; Drag to pan &middot; Click node to visit profile
        </div>
      </div>
    </div>
  )
}
