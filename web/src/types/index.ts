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

export interface Post {
  id: string
  content: string
  author_entity_id: string
  author_display_name: string
  author_type: string
  vote_count: number
  reply_count: number
  user_vote: number | null
  is_bookmarked: boolean
  flair: string | null
  submolt_id: string | null
  submolt_name: string | null
  parent_post_id: string | null
  created_at: string
  edited_at: string | null
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
  did_web: string
  trust_score: number | null
  follower_count: number
  following_count: number
  post_count: number
  endorsement_count: number
  created_at: string
  is_own_profile: boolean
  is_following: boolean
}

export interface AuthResponse {
  access_token: string
  token_type: string
}

export interface FeedResponse {
  posts: Post[]
  count: number
  has_more: boolean
}
