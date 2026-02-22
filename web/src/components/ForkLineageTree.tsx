import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../lib/api'

interface LineageNode {
  entity_id: string
  display_name: string
  version: string
  parent_entity_id: string | null
  created_at: string
}

export default function ForkLineageTree({ entityId }: { entityId: string }) {
  const { data } = useQuery<{ lineage: LineageNode[] }>({
    queryKey: ['fork-lineage', entityId],
    queryFn: async () => {
      const { data } = await api.get(`/evolution/${entityId}/lineage`)
      return data
    },
    enabled: !!entityId,
  })

  if (!data?.lineage || data.lineage.length <= 1) return null

  const parent = data.lineage.find((n) => n.parent_entity_id === null) || data.lineage[0]
  const children = data.lineage.filter((n) => n.entity_id !== parent.entity_id)

  return (
    <div className="mt-4 bg-surface border border-border rounded-lg p-4">
      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
        Fork Lineage
      </h3>
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-primary shrink-0" />
          <Link
            to={`/profile/${parent.entity_id}`}
            className={`text-sm font-medium hover:text-primary-light transition-colors ${
              parent.entity_id === entityId ? 'text-primary-light' : ''
            }`}
          >
            {parent.display_name}
          </Link>
          <span className="text-xs text-text-muted">{parent.version}</span>
          {parent.entity_id === entityId && (
            <span className="text-[10px] text-primary-light bg-primary/10 px-1.5 py-0.5 rounded">current</span>
          )}
        </div>
        {children.map((child) => (
          <div key={child.entity_id} className="flex items-center gap-2 ml-6">
            <div className="w-px h-4 bg-border -mt-4 mr-1" />
            <div className="w-1.5 h-1.5 rounded-full bg-accent shrink-0" />
            <Link
              to={`/profile/${child.entity_id}`}
              className={`text-sm hover:text-primary-light transition-colors ${
                child.entity_id === entityId ? 'font-medium text-primary-light' : ''
              }`}
            >
              {child.display_name}
            </Link>
            <span className="text-xs text-text-muted">{child.version}</span>
            {child.entity_id === entityId && (
              <span className="text-[10px] text-primary-light bg-primary/10 px-1.5 py-0.5 rounded">current</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
