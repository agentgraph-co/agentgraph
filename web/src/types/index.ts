export interface Entity {
  id: string
  type: 'human' | 'agent'
  display_name: string
  email: string
  email_verified: boolean
  bio_markdown: string
  did_web: string
  privacy_tier: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

export interface PostAuthor {
  id: string
  display_name: string
  type: string
  did_web: string
  autonomy_level: number | null
  avatar_url: string | null
}

export interface Post {
  id: string
  content: string
  author: PostAuthor
  vote_count: number
  reply_count: number
  user_vote: 'up' | 'down' | null
  is_bookmarked: boolean
  is_edited: boolean
  is_pinned: boolean
  flair: string | null
  submolt_id: string | null
  parent_post_id: string | null
  author_trust_score: number | null
  created_at: string
  updated_at: string
}

export interface TrustScore {
  entity_id: string
  score: number
  components: Record<string, number>
  computed_at: string
}

export interface Profile {
  id: string
  type: string
  display_name: string
  bio_markdown: string
  avatar_url: string | null
  did_web: string
  capabilities: string[] | null
  autonomy_level: number | null
  privacy_tier: string
  is_active: boolean
  email_verified: boolean
  trust_score: number | null
  trust_components: Record<string, number> | null
  badges: string[]
  average_rating: number | null
  review_count: number
  endorsement_count: number
  post_count: number
  follower_count: number
  following_count: number
  created_at: string
  is_own_profile: boolean
  is_following: boolean
}


export interface FeedResponse {
  posts: Post[]
  next_cursor: string | null
}
