/**
 * Graph visual constants — Catppuccin Mocha palette for cluster coloring,
 * node sizing by trust, edge styling by relationship type.
 */

/** Catppuccin Mocha palette — 12 distinct cluster colors */
export const CLUSTER_COLORS = [
  '#89b4fa', // Blue
  '#f38ba8', // Red (Maroon)
  '#a6e3a1', // Green
  '#f9e2af', // Yellow
  '#cba6f7', // Mauve
  '#fab387', // Peach
  '#94e2d5', // Teal
  '#f5c2e7', // Pink
  '#74c7ec', // Sapphire
  '#eba0ac', // Flamingo
  '#b4befe', // Lavender
  '#89dceb', // Sky
] as const

/** Default color for nodes without a cluster assignment */
export const UNCLUSTERED_COLOR = '#585b70'

/** Map a cluster_id to a color (wraps around if > 12 clusters) */
export function clusterColor(clusterId: number | null | undefined): string {
  if (clusterId == null) return UNCLUSTERED_COLOR
  return CLUSTER_COLORS[clusterId % CLUSTER_COLORS.length]
}

/** Edge type colors */
export const EDGE_COLORS: Record<string, string> = {
  follow: '#585b70',
  attestation: '#2DD4BF',
  operator_agent: '#f9e2af',
  collaboration: '#cba6f7',
  service: '#fab387',
  fork: '#f5c2e7',
}

/** Default edge color fallback */
export const DEFAULT_EDGE_COLOR = '#45475a'

/** Get edge color by relationship type */
export function edgeColor(type: string): string {
  return EDGE_COLORS[type] ?? DEFAULT_EDGE_COLOR
}

/** Node radius from trust score.
 *  - Base: 4px (no trust score)
 *  - Range: 4-16px based on trust (0.0-1.0)
 */
export function nodeRadius(trustScore: number | null | undefined): number {
  if (trustScore == null) return 4
  return 4 + trustScore * 12
}

/** Node type colors (used when clusters not available) */
export const NODE_TYPE_COLORS: Record<string, string> = {
  agent: '#2DD4BF',
  human: '#a6e3a1',
}

/** Canvas background color (dark theme) */
export const GRAPH_BG = '#11111b'

/** Label visibility thresholds based on zoom level */
export const ZOOM_THRESHOLDS = {
  showLabels: 1.5,
  showDetails: 2.5,
} as const

/** Glow ring opacity for cluster membership */
export const CLUSTER_GLOW_ALPHA = 0.25

/** Edge particle settings for directional flow */
export const PARTICLE_CONFIG = {
  width: 2,
  speed: 0.004,
  count: {
    attestation: 3,
    follow: 1,
    operator_agent: 2,
    collaboration: 2,
    service: 2,
    fork: 1,
  } as Record<string, number>,
} as const

/** Default particle count for unknown edge types */
export const DEFAULT_PARTICLE_COUNT = 1
