import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { InlineSkeleton } from '../../components/Skeleton'

export default function WaitlistTab() {
  const { data: waitlistData, isLoading: waitlistLoading } = useQuery<{
    entries: { email: string; submitted_at: string; page: string; session_id: string }[]
    total: number
  }>({
    queryKey: ['admin-waitlist'],
    queryFn: async () => {
      const { data } = await api.get('/admin/waitlist')
      return data
    },
    staleTime: 30_000,
  })

  return (
    <div>
      <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
        iOS TestFlight Waitlist
      </h2>

      {waitlistLoading ? (
        <div className="py-10"><InlineSkeleton /></div>
      ) : waitlistData && waitlistData.entries.length > 0 ? (
        <div className="space-y-2">
          <div className="text-xs text-text-muted mb-3">
            {waitlistData.total} signup{waitlistData.total !== 1 ? 's' : ''}
          </div>
          <div className="bg-surface border border-border rounded-lg overflow-x-auto">
            <table className="w-full text-sm min-w-[400px]">
              <caption className="sr-only">iOS TestFlight waitlist signups</caption>
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Email</th>
                  <th className="px-4 py-2 text-xs text-text-muted font-medium">Signed Up</th>
                </tr>
              </thead>
              <tbody>
                {waitlistData.entries.map((entry, i) => (
                  <tr key={`${entry.email}-${i}`} className="border-b border-border/50 last:border-0">
                    <td className="px-4 py-2.5 font-mono text-xs">{entry.email}</td>
                    <td className="px-4 py-2.5 text-xs text-text-muted">
                      {new Date(entry.submitted_at).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                        hour: 'numeric',
                        minute: '2-digit',
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="text-text-muted text-center py-10">No signups yet</div>
      )}
    </div>
  )
}
