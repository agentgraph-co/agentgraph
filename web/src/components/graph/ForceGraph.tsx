/**
 * Force-directed graph visualization using react-force-graph.
 * 2D Canvas (default, handles 5000+ nodes) with optional 3D WebGL toggle.
 * Nodes sized by trust score, colored by cluster_id.
 * Trust edges pulse with directional particles.
 * LOD: labels at zoom > 1.5, details at zoom > 2.5.
 */
import { useRef, useState, useCallback, useEffect, useMemo } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import ForceGraph3D from 'react-force-graph-3d'
import type { GraphData, GraphNode, GraphEdge } from '../../hooks/useGraphData'
import {
  clusterColor,
  edgeColor,
  nodeRadius,
  GRAPH_BG,
  ZOOM_THRESHOLDS,
  CLUSTER_GLOW_ALPHA,
  PARTICLE_CONFIG,
  DEFAULT_PARTICLE_COUNT,
  NODE_TYPE_COLORS,
} from '../../lib/graphTheme'

// Internal node shape used by react-force-graph (adds x, y, etc.)
interface FGNode extends GraphNode {
  x?: number
  y?: number
  z?: number
  vx?: number
  vy?: number
  vz?: number
}

interface FGLink extends GraphEdge {
  // react-force-graph resolves source/target to node objects at runtime
}

interface ForceGraphData {
  nodes: FGNode[]
  links: FGLink[]
}

interface ForceGraphProps {
  graphData: GraphData
  is3D: boolean
  searchTerm: string
  activeCluster: number | null
  onNodeClick?: (node: GraphNode) => void
  onNodeHover?: (node: GraphNode | null, position: { x: number; y: number }) => void
  onBackgroundClick?: () => void
}

/** Convert API GraphData (edges) to react-force-graph format (links) */
function toForceGraphData(
  data: GraphData,
  filterType: string,
  activeCluster: number | null,
): ForceGraphData {
  let nodes = [...data.nodes]
  if (filterType !== 'all') {
    nodes = nodes.filter((n) => n.type === filterType)
  }
  if (activeCluster !== null) {
    nodes = nodes.filter((n) => n.cluster_id === activeCluster)
  }

  const nodeIds = new Set(nodes.map((n) => n.id))
  const links = data.edges.filter(
    (e) => nodeIds.has(e.source) && nodeIds.has(e.target),
  )

  return { nodes, links }
}

export default function ForceGraph({
  graphData,
  is3D,
  searchTerm,
  activeCluster,
  onNodeClick,
  onNodeHover,
  onBackgroundClick,
}: ForceGraphProps) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [currentZoom, setCurrentZoom] = useState(1)

  // Track dimensions
  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setDimensions({ width: Math.floor(width), height: Math.floor(height) })
      }
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  // Zoom tracking — store the current zoom level from the engine
  const handleZoom = useCallback((transform: { k: number }) => {
    setCurrentZoom(transform.k)
  }, [])

  // Search term lowered for matching
  const searchLower = searchTerm.toLowerCase().trim()

  // Build the data for react-force-graph
  const fgData = useMemo(
    () => toForceGraphData(graphData, 'all', activeCluster),
    [graphData, activeCluster],
  )

  // Node color callback
  const getNodeColor = useCallback(
    (node: object) => {
      const n = node as FGNode
      // Search highlight
      if (searchLower && n.label.toLowerCase().includes(searchLower)) {
        return '#f38ba8'
      }
      // Cluster color
      if (n.cluster_id != null) {
        return clusterColor(n.cluster_id)
      }
      // Fallback: type-based color
      return NODE_TYPE_COLORS[n.type] ?? '#585b70'
    },
    [searchLower],
  )

  // Node size callback
  const getNodeVal = useCallback((node: object) => {
    const n = node as FGNode
    const r = nodeRadius(n.trust_score)
    // react-force-graph uses val as area-proportional; we square the radius
    return r * r * 0.5
  }, [])

  // Custom 2D canvas node painting — includes cluster glow ring and LOD labels
  const paintNode = useCallback(
    (node: object, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as FGNode
      if (n.x == null || n.y == null) return

      const r = nodeRadius(n.trust_score)
      const color = getNodeColor(n)

      // Cluster glow ring
      if (n.cluster_id != null) {
        const glowR = r + 3
        ctx.beginPath()
        ctx.arc(n.x, n.y, glowR, 0, 2 * Math.PI)
        const cc = clusterColor(n.cluster_id)
        ctx.fillStyle = cc + Math.round(CLUSTER_GLOW_ALPHA * 255).toString(16).padStart(2, '0')
        ctx.fill()
      }

      // Node circle
      ctx.beginPath()
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI)
      ctx.fillStyle = color
      ctx.fill()
      ctx.strokeStyle = '#11111b'
      ctx.lineWidth = 1
      ctx.stroke()

      // Search highlight ring
      if (searchLower && n.label.toLowerCase().includes(searchLower)) {
        ctx.beginPath()
        ctx.arc(n.x, n.y, r + 2, 0, 2 * Math.PI)
        ctx.strokeStyle = '#f38ba8'
        ctx.lineWidth = 2
        ctx.stroke()
      }

      // LOD: Labels at zoom > 1.5
      if (globalScale >= ZOOM_THRESHOLDS.showLabels) {
        ctx.font = `${Math.min(12, 10 / globalScale * 3)}px Geist, sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillStyle = '#cdd6f4'
        ctx.fillText(n.label, n.x, n.y + r + 2)
      }

      // LOD: Details at zoom > 2.5 (trust score badge)
      if (globalScale >= ZOOM_THRESHOLDS.showDetails && n.trust_score != null) {
        const trustLabel = `${(n.trust_score * 100).toFixed(0)}%`
        ctx.font = `${8 / globalScale * 3}px Geist, sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'
        ctx.fillStyle = '#6c7086'
        ctx.fillText(trustLabel, n.x, n.y - r - 2)
      }
    },
    [getNodeColor, searchLower],
  )

  // Edge color
  const getLinkColor = useCallback((link: object) => {
    const l = link as FGLink
    return edgeColor(l.type)
  }, [])

  // Directional particle count per edge type
  const getLinkParticles = useCallback((link: object) => {
    const l = link as FGLink
    return PARTICLE_CONFIG.count[l.type] ?? DEFAULT_PARTICLE_COUNT
  }, [])

  // Handle node click
  const handleNodeClick = useCallback(
    (node: object) => {
      onNodeClick?.(node as FGNode)
    },
    [onNodeClick],
  )

  // Handle node hover
  const handleNodeHover = useCallback(
    (node: object | null, previousNode?: object | null) => {
      void previousNode
      if (node == null) {
        onNodeHover?.(null, { x: 0, y: 0 })
        return
      }
      const n = node as FGNode
      // Estimate screen position from node coords
      // The actual screen position is approximate; for the tooltip we rely
      // on the mouse event position captured by the container overlay.
      onNodeHover?.(n, { x: 0, y: 0 })
    },
    [onNodeHover],
  )

  // 3D node color (THREE.js compatible — just a hex string)
  const getNodeColor3D = useCallback(
    (node: object) => {
      return getNodeColor(node)
    },
    [getNodeColor],
  )

  // Common props for both 2D and 3D
  const commonProps = {
    graphData: fgData,
    nodeId: 'id' as const,
    nodeLabel: 'label' as const,
    nodeColor: is3D ? getNodeColor3D : undefined,
    nodeVal: getNodeVal,
    linkSource: 'source' as const,
    linkTarget: 'target' as const,
    linkColor: getLinkColor,
    linkDirectionalParticles: getLinkParticles,
    linkDirectionalParticleWidth: PARTICLE_CONFIG.width,
    linkDirectionalParticleSpeed: PARTICLE_CONFIG.speed,
    linkOpacity: 0.45,
    linkWidth: 1.5,
    onNodeClick: handleNodeClick,
    onNodeHover: handleNodeHover,
    onBackgroundClick: onBackgroundClick,
    backgroundColor: GRAPH_BG,
    width: dimensions.width,
    height: dimensions.height,
    warmupTicks: 50,
    cooldownTime: 3000,
  }

  return (
    <div ref={containerRef} className="w-full h-full relative">
      {is3D ? (
        <ForceGraph3D
          ref={fgRef as React.MutableRefObject<never>}
          {...commonProps}
          nodeOpacity={0.9}
          linkDirectionalParticleColor={getLinkColor}
        />
      ) : (
        <ForceGraph2D
          ref={fgRef as React.MutableRefObject<never>}
          {...commonProps}
          nodeCanvasObject={paintNode}
          nodeCanvasObjectMode={() => 'replace' as const}
          onZoom={handleZoom}
          linkDirectionalParticleColor={getLinkColor}
        />
      )}

      {/* Controls hint + actions */}
      <div className="absolute bottom-3 left-3 flex items-center gap-3">
        <span className="text-[10px] text-text-muted/50 pointer-events-none">
          Scroll to zoom &middot; Drag to pan &middot; Click node for actions
          {!is3D && ` · Zoom: ${currentZoom.toFixed(1)}x`}
        </span>
      </div>
      <div className="absolute bottom-3 right-3 flex items-center gap-1.5">
        <button
          onClick={() => fgRef.current?.zoomToFit(400, 40)}
          className="px-2 py-1 rounded text-[10px] bg-surface/80 text-text-muted hover:text-text border border-border/50 cursor-pointer transition-colors"
          title="Fit all nodes in view"
        >
          Fit
        </button>
        <button
          onClick={() => { fgRef.current?.centerAt(0, 0, 400); fgRef.current?.zoom(1, 400) }}
          className="px-2 py-1 rounded text-[10px] bg-surface/80 text-text-muted hover:text-text border border-border/50 cursor-pointer transition-colors"
          title="Reset zoom and center"
        >
          Reset
        </button>
      </div>
    </div>
  )
}
