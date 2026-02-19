import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
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

export default function Graph() {
  const svgRef = useRef<SVGSVGElement>(null)

  const { data, isLoading } = useQuery<GraphData>({
    queryKey: ['graph'],
    queryFn: async () => {
      const { data } = await api.get('/graph', { params: { limit: 200 } })
      return data
    },
  })

  useEffect(() => {
    if (!data || !svgRef.current) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight

    const g = svg.append('g')

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })
    svg.call(zoom)

    // Color scale
    const color = (type: string) => type === 'agent' ? '#89b4fa' : '#a6e3a1'
    const radius = (node: GraphNode) => {
      const base = node.trust_score ? 4 + node.trust_score * 8 : 6
      return base
    }

    // Build simulation
    const simulation = d3.forceSimulation<GraphNode>(data.nodes)
      .force('link', d3.forceLink<GraphNode, d3.SimulationLinkDatum<GraphNode>>(
        data.edges.map(e => ({ source: e.source, target: e.target }))
      ).id((d) => d.id).distance(60))
      .force('charge', d3.forceManyBody().strength(-120))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(12))

    // Edges
    const link = g.append('g')
      .selectAll('line')
      .data(data.edges)
      .join('line')
      .attr('stroke', '#313244')
      .attr('stroke-opacity', 0.4)
      .attr('stroke-width', 1)

    // Nodes
    const node = g.append('g')
      .selectAll<SVGCircleElement, GraphNode>('circle')
      .data(data.nodes)
      .join('circle')
      .attr('r', (d) => radius(d))
      .attr('fill', (d) => color(d.type))
      .attr('stroke', '#11111b')
      .attr('stroke-width', 1.5)
      .style('cursor', 'pointer')

    // Labels
    const label = g.append('g')
      .selectAll('text')
      .data(data.nodes)
      .join('text')
      .text((d) => d.label)
      .attr('font-size', '9px')
      .attr('fill', '#6c7086')
      .attr('text-anchor', 'middle')
      .attr('dy', (d) => radius(d) + 12)

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

    // Tooltip on hover
    node.append('title').text((d) =>
      `${d.label} (${d.type})${d.trust_score !== null ? `\nTrust: ${(d.trust_score * 100).toFixed(0)}%` : ''}`
    )

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
  }, [data])

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading graph...</div>
  }

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)]">
      <div className="flex items-center justify-between mb-3">
        <h1 className="text-xl font-bold">Trust Graph</h1>
        {data && (
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <span>{data.node_count} entities</span>
            <span>{data.edge_count} connections</span>
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-success" />
              <span>Human</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-accent" />
              <span>Agent</span>
            </div>
          </div>
        )}
      </div>
      <div className="flex-1 bg-surface border border-border rounded-lg overflow-hidden">
        <svg
          ref={svgRef}
          className="w-full h-full"
          style={{ background: '#11111b' }}
        />
      </div>
    </div>
  )
}
