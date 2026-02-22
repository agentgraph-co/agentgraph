/**
 * TanStack Query hooks for the graph API endpoints.
 */
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

// ── Response types ──

export interface GraphNode {
  id: string
  label: string
  type: string
  trust_score: number | null
  is_active?: boolean
  cluster_id?: number | null
  avatar_url?: string | null
}

export interface GraphEdge {
  source: string
  target: string
  type: string
  weight?: number | null
  attestation_type?: string | null
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  node_count: number
  edge_count: number
}

export interface ClusterInfo {
  cluster_id: number
  size: number
  avg_trust: number
  member_count: number
  dominant_type: string
}

export interface ClustersResponse {
  clusters: ClusterInfo[]
  total_clusters: number
}

export interface TrustFlowAttestation {
  attester_id: string
  attester_name: string
  attestation_type: string
  weight: number
  children: TrustFlowAttestation[]
}

export interface TrustFlowResponse {
  entity_id: string
  trust_score: number | null
  attestations: TrustFlowAttestation[]
}

export interface LineageNode {
  entity_id: string
  entity_name: string
  version: string | null
  children: LineageNode[]
}

export interface NetworkStats {
  total_entities: number
  total_humans: number
  total_agents: number
  total_follows: number
  avg_followers: number
  avg_following: number
  most_followed: { id: string; display_name: string; type: string; follower_count: number }[]
  most_connected: { id: string; display_name: string; type: string; connection_count: number }[]
}

// ── Hooks ──

/** Fetch the rich graph with multi-edge types and cluster IDs */
export function useRichGraph(options?: {
  limit?: number
  entityType?: string | null
  minTrust?: number | null
  enabled?: boolean
}) {
  const params: Record<string, string | number> = {}
  if (options?.limit) params.limit = options.limit
  if (options?.entityType) params.entity_type = options.entityType
  if (options?.minTrust != null) params.min_trust = options.minTrust

  return useQuery<GraphData>({
    queryKey: ['graph-rich', params],
    queryFn: async () => {
      const { data } = await api.get('/graph/rich', { params })
      return data
    },
    enabled: options?.enabled !== false,
  })
}

/** Fetch cluster metadata for the legend */
export function useGraphClusters(enabled = true) {
  return useQuery<ClustersResponse>({
    queryKey: ['graph-clusters'],
    queryFn: async () => {
      const { data } = await api.get('/graph/clusters')
      return data
    },
    enabled,
  })
}

/** Fetch trust attestation chain tree */
export function useTrustFlow(entityId: string | null, depth = 2) {
  return useQuery<TrustFlowResponse>({
    queryKey: ['trust-flow', entityId, depth],
    queryFn: async () => {
      const { data } = await api.get(`/graph/trust-flow/${entityId}`, {
        params: { depth },
      })
      return data
    },
    enabled: !!entityId,
  })
}

/** Fetch evolution fork tree */
export function useLineageTree(entityId: string | null) {
  return useQuery<LineageNode>({
    queryKey: ['lineage-tree', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/graph/lineage-tree/${entityId}`)
      return data
    },
    enabled: !!entityId,
  })
}

/** Fetch enhanced ego graph with multi-edge types */
export function useEgoGraph(entityId: string | null, depth = 1) {
  return useQuery<GraphData>({
    queryKey: ['ego-rich', entityId, depth],
    queryFn: async () => {
      const { data } = await api.get(`/graph/ego/${entityId}/rich`, {
        params: { depth },
      })
      return data
    },
    enabled: !!entityId,
  })
}

/** Fetch network stats */
export function useNetworkStats(enabled = true) {
  return useQuery<NetworkStats>({
    queryKey: ['graph-stats'],
    queryFn: async () => {
      const { data } = await api.get('/graph/stats')
      return data
    },
    enabled,
  })
}
