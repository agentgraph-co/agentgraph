/**
 * Graph visual constants — Catppuccin Mocha palette for cluster coloring,
 * node sizing by trust, edge styling by relationship type.
 * Supports dark and light themes.
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
export const UNCLUSTERED_COLOR = '#7f849c'
export const UNCLUSTERED_COLOR_LIGHT = '#94a3b8'

/** Map a cluster_id to a color (wraps around if > 12 clusters) */
export function clusterColor(clusterId: number | null | undefined): string {
  if (clusterId == null) return UNCLUSTERED_COLOR
  return CLUSTER_COLORS[clusterId % CLUSTER_COLORS.length]
}

/** Edge type colors (dark theme) */
export const EDGE_COLORS: Record<string, string> = {
  follow: '#7f849c',
  attestation: '#2DD4BF',
  operator_agent: '#f9e2af',
  collaboration: '#cba6f7',
  service: '#fab387',
  fork: '#f5c2e7',
}

/** Edge type colors (light theme) — darkened for visibility against #f1f5f9 bg */
export const EDGE_COLORS_LIGHT: Record<string, string> = {
  follow: '#64748b',
  attestation: '#0f766e',
  operator_agent: '#a16207',
  collaboration: '#6d28d9',
  service: '#c2410c',
  fork: '#86198f',
}

/** Default edge color fallback */
export const DEFAULT_EDGE_COLOR = '#6c7086'
export const DEFAULT_EDGE_COLOR_LIGHT = '#64748b'

/** Get edge color by relationship type, theme-aware */
export function edgeColor(type: string, theme: 'dark' | 'light' = 'dark'): string {
  const colors = theme === 'light' ? EDGE_COLORS_LIGHT : EDGE_COLORS
  const fallback = theme === 'light' ? DEFAULT_EDGE_COLOR_LIGHT : DEFAULT_EDGE_COLOR
  return colors[type] ?? fallback
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

/** Canvas background colors */
export const GRAPH_BG = '#11111b'
export const GRAPH_BG_LIGHT = '#f1f5f9'

/** Label / badge colors per theme */
export const GRAPH_LABEL_DARK = '#cdd6f4'
export const GRAPH_LABEL_LIGHT = '#1e293b'
export const GRAPH_BADGE_DARK = '#9399b2'
export const GRAPH_BADGE_LIGHT = '#64748b'

/** Node stroke colors per theme */
export const GRAPH_NODE_STROKE_DARK = '#11111b'
export const GRAPH_NODE_STROKE_LIGHT = '#e2e8f0'

/** Label visibility thresholds based on zoom level */
export const ZOOM_THRESHOLDS = {
  showLabels: 0.8,
  showDetails: 1.5,
} as const

/** Glow ring opacity for cluster membership */
export const CLUSTER_GLOW_ALPHA = 0.35

/** Edge particle settings for directional flow — subtle glowing dots */
export const PARTICLE_CONFIG = {
  width: 2,
  speed: 0.003,
  count: {
    attestation: 2,
    follow: 1,
    operator_agent: 2,
    collaboration: 2,
    service: 1,
    fork: 1,
  } as Record<string, number>,
} as const

/** Default particle count for unknown edge types */
export const DEFAULT_PARTICLE_COUNT = 1
