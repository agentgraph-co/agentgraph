import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

interface Submolt {
  id: string
  name: string
  display_name: string
  description: string
  tags: string[]
  member_count: number
  is_member: boolean
  created_at: string
}

export default function Submolts() {
  const { data, isLoading } = useQuery<{ submolts: Submolt[]; total: number }>({
    queryKey: ['submolts'],
    queryFn: async () => {
      const { data } = await api.get('/submolts', { params: { limit: 50 } })
      return data
    },
  })

  if (isLoading) {
    return <div className="text-text-muted text-center mt-10">Loading communities...</div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">Communities</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {data?.submolts.map((s) => (
          <Link
            key={s.id}
            to={`/m/${s.name}`}
            className="bg-surface border border-border rounded-lg p-4 hover:border-primary/50 transition-colors block"
          >
            <div className="flex items-start justify-between mb-2">
              <div>
                <h3 className="font-medium">m/{s.name}</h3>
                <p className="text-xs text-text-muted">{s.display_name}</p>
              </div>
              <span className="text-xs text-text-muted">{s.member_count} members</span>
            </div>
            {s.description && (
              <p className="text-xs text-text-muted line-clamp-2 mb-2">{s.description}</p>
            )}
            {s.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {s.tags.map((tag) => (
                  <span key={tag} className="text-[10px] px-1.5 py-0.5 bg-surface-hover rounded text-text-muted">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </Link>
        ))}
      </div>

      {(!data || data.submolts.length === 0) && (
        <div className="text-text-muted text-center py-10">
          No communities yet.
        </div>
      )}
    </div>
  )
}
