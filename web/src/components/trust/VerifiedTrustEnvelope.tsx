/**
 * VerifiedTrustEnvelope — fetches a subject's signed Trust Score v2 envelope by
 * DID and renders it via the shared TrustEnvelopePanel (design §6.1).
 *
 * Renders nothing if no envelope is available yet (404 = subject has no
 * resolvable v2 signals), so it never disturbs the existing trust display.
 */
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import TrustEnvelopePanel, { type TrustEnvelope } from './TrustEnvelopePanel'

export default function VerifiedTrustEnvelope({ did }: { did: string }) {
  const { data: env } = useQuery<TrustEnvelope>({
    queryKey: ['aggregate-envelope', did],
    queryFn: async () => {
      const { data } = await api.get(`/aggregate/${encodeURIComponent(did)}`)
      return data
    },
    enabled: !!did,
    staleTime: 5 * 60_000,
    retry: false, // 404 = no v2 envelope yet; render nothing rather than retry
  })

  if (!env) return null

  return (
    <TrustEnvelopePanel
      env={env}
      verifyHref={`/api/v1/aggregate/${encodeURIComponent(did)}/verify`}
    />
  )
}
