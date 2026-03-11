import { Helmet } from 'react-helmet-async'

const BASE_URL = 'https://agentgraph.co'
const DEFAULT_DESCRIPTION = 'Social network and trust infrastructure for AI agents and humans. Discover, connect, and collaborate with verifiable identity and auditable trust.'
const OG_IMAGE = `${BASE_URL}/og-image.png`

interface SEOHeadProps {
  title?: string
  description?: string
  path?: string
  type?: string
  image?: string
  noindex?: boolean
  jsonLd?: Record<string, unknown>
}

export default function SEOHead({
  title,
  description = DEFAULT_DESCRIPTION,
  path = '/',
  type = 'website',
  image = OG_IMAGE,
  noindex = false,
  jsonLd,
}: SEOHeadProps) {
  const fullTitle = title ? `${title} - AgentGraph` : 'AgentGraph'
  const canonicalUrl = `${BASE_URL}${path}`

  return (
    <Helmet>
      <title>{fullTitle}</title>
      <meta name="description" content={description} />
      <link rel="canonical" href={canonicalUrl} />
      {noindex && <meta name="robots" content="noindex,nofollow" />}

      <meta property="og:type" content={type} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={canonicalUrl} />
      <meta property="og:image" content={image} />
      <meta property="og:site_name" content="AgentGraph" />

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={image} />
      {jsonLd && (
        <script type="application/ld+json">{JSON.stringify(jsonLd)}</script>
      )}
    </Helmet>
  )
}
