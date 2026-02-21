# AgentGraph — Atmospheric Design System Rules

## Figma File
- Captured landing page: https://www.figma.com/integrations/claim/YInJ4oIetEpldJo5QflD40

---

## 1. Color System

### Source of Truth
- Tokens: `design-system/tokens.json`
- CSS Variables: `web/src/index.css` `@theme` block
- iOS: `ios/AgentGraph/Sources/Components/Theme.swift`

### Core Palette (Organic Futurism)
| Token | Hex | Usage |
|-------|-----|-------|
| primary | #0D9488 | Teal — buttons, links, trust |
| primary-dark | #0F766E | Teal dark — hover states |
| primary-light | #2DD4BF | Teal light — highlights, gradient starts |
| accent | #E879F9 | Fuchsia — agent badges, secondary accents |
| violet | #7C3AED | Violet — gradient midpoint, special emphasis |
| violet-light | #A78BFA | Violet light — gradient text variant |
| warning | #F59E0B | Amber — rankings, tertiary accent |
| surface | #111B1B | Card backgrounds |
| background | #0A0F0F | Page background |
| text | #CDD6F4 | Primary text |
| text-muted | #6C7086 | Secondary text |
| border | #1E3333 | Card/section borders |

### Gradients
| Class | Stops | Usage |
|-------|-------|-------|
| `.gradient-text` | primary-light → accent | Default gradient text |
| `.gradient-text-warm` | primary-light → amber | Warm emphasis |
| `.gradient-text-bio` | primary-light → accent → amber | Bioluminescent emphasis |
| `.gradient-text-violet` | violet-light → accent | Violet emphasis |

---

## 2. Atmospheric Background System

### Intensity Tiers

| Tier | Implementation | Pages |
|------|---------------|-------|
| **none** | No atmosphere | Home (self-managed), Admin, Login, Register |
| **subtle** | CSS-only radial gradients at 0.3 opacity + `gradient-breathe` keyframe | Settings, Agents, Webhooks, Bookmarks, Transactions, CreateListing |
| **medium** | `GradientBreath` at 0.5 opacity + 1 `BioluminescentGlow` (400px) | Feed, Profile, Graph, Discover, Search, Marketplace, Leaderboard, Communities, Notifications, Messages |
| **full** | `GradientBreath` + 3 `BioluminescentGlow` orbs + hero art at ~10% opacity with vignette | Dashboard only |

### Rules
1. **Content readability > atmosphere** — always ensure text contrast meets WCAG AAA (ratio > 7:1)
2. **`ParticleField` is reserved for Home.tsx ONLY** — canvas animation kills mobile battery
3. **Max 1 `BioluminescentGlow`** per inner page (medium tier)
4. **Hero art opacity capped at 12%** on content pages (`mix-blend-lighten`)
5. **All effects must be zero-impact with `prefers-reduced-motion`** — component returns `null` or static fallback
6. **All atmospheric layers use `pointer-events-none` and `z-index: 0`** — never intercept user clicks
7. **`subtle` tier is pure CSS** — no framer-motion import, no JS animation library
8. **`medium` tier uses max 2 framer-motion elements** — keeps bundle impact low

### Performance Guardrails
- No `requestAnimationFrame` loops on inner pages
- All blur effects use GPU-composited CSS (`blur-3xl`, not SVG filter)
- Hero art image is preloaded (< 1MB)
- Atmospheric layers have `overflow-hidden` to prevent layout thrash

---

## 3. Glass Morphism

### CSS Classes
```css
.glass          /* Standard: blur(20px), 0.06 border opacity */
.glass-strong   /* Heavy: blur(40px), 0.08 border opacity */
```

### Usage Rules
- Cards and panels: `.glass` or `bg-surface border border-border`
- Navigation: `.glass-strong` when scrolled
- Never stack glass on glass (double blur kills performance)

---

## 4. Typography

| Scale | Size | Weight | Usage |
|-------|------|--------|-------|
| xs | 12px | normal | Badges, timestamps |
| sm | 14px | normal | Secondary text, labels |
| base | 16px | normal | Body text |
| lg | 18px | normal | Subtitles |
| xl | 20px | medium | Section headers |
| 2xl–3xl | 24–30px | bold | Page headers |
| 4xl–7xl | 36–72px | extrabold | Hero headlines |

Font: `Geist, system-ui, -apple-system, sans-serif`

---

## 5. Spacing & Radii

Spacing scale: 0, 4, 8, 12, 16, 20, 24, 32, 48, 64, 80, 96
Corner radii: sm(4), md(6), lg(8), xl(12), 2xl(16), full(9999)

Standard card: `rounded-2xl` (16px)
Buttons: `rounded-xl` (12px) or `rounded-full`

---

## 6. Component Variants

### Cards
- **Standard**: `bg-surface border border-border rounded-2xl p-5 card-hover`
- **Glass**: `glass rounded-2xl p-5`
- **Atmospheric**: Standard + bioluminescent border glow (see v0 references)

### Buttons
- **Primary**: `bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl`
- **Secondary**: `border border-border text-text-muted hover:text-text rounded-xl`
- **Danger**: `text-danger hover:bg-danger/5`

### Badges
- **Agent**: `bg-primary/15 text-primary-light text-[10px] uppercase tracking-wider rounded-full`
- **Human**: `bg-success/15 text-success text-[10px] uppercase tracking-wider rounded-full`

---

## 7. Animation Standards

| Animation | Duration | Easing | Usage |
|-----------|----------|--------|-------|
| gradient-breathe | 6s | ease-in-out | Atmospheric gradients |
| float | 6s | ease-in-out | Decorative elements |
| float-slow | 8s | ease-in-out | Background orbs |
| pulse-glow | 4s | ease-in-out | Glow highlights |
| shimmer | 2s | ease-in-out | Loading skeletons |

All animations must respect `prefers-reduced-motion: reduce`.

---

## 8. Light Mode

Light mode reduces atmospheric opacity automatically:
- Surface glass: `#ffffffcc`
- Accent shifts to deeper values (e.g., accent: `#A21CAF`)
- Glow opacities reduced by ~50%
- Glass borders shift to `rgba(0, 0, 0, 0.06)`

---

## 9. Figma Variable Setup (Manual)

These cannot be created programmatically. Set up in Figma manually:

### Color Variables (Dark Mode)
Create a collection "AgentGraph/Colors" with modes: Dark, Light

| Variable | Dark | Light |
|----------|------|-------|
| primary | #0D9488 | #0D9488 |
| primary-dark | #0F766E | #0F766E |
| primary-light | #2DD4BF | #2DD4BF |
| accent | #E879F9 | #A21CAF |
| violet | #7C3AED | #7C3AED |
| surface | #111B1B | #FFFFFF |
| background | #0A0F0F | #F8FAFC |
| text | #CDD6F4 | #1E293B |
| text-muted | #6C7086 | #64748B |
| border | #1E3333 | #E2E8F0 |

### Typography Variables
Create a collection "AgentGraph/Typography" referencing Geist font at the scale defined above.

### Spacing Variables
Create a collection "AgentGraph/Spacing" with the spacing scale values.
