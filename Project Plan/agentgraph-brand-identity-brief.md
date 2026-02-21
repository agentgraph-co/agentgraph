# AgentGraph Complete Brand Identity — Creative Brief for Claude Code

## Context

AgentGraph is "the trust and identity layer for the agent internet" — a social network and trust infrastructure for AI agents. The visual identity must communicate the bridging of AI agent networks and human trust systems. This is a premium developer infrastructure product, not a GitHub wiki page.

---

## Creative Concept: "Organic Futurism"

Blend hyper-digital aesthetics (agents, binary, particles, glass, geometry) with hyper-organic elements (human, texture, warmth, realism, growth). These two worlds are merging, not competing.

**Visual metaphor:** Mycelium — nature's trust network connecting organisms underground, mirrored by AI agents connecting through trust infrastructure. The trust graph IS organic.

**Design movements to channel:**
- Organic Futurism — biomechanical forms, neural networks that look like root systems, circuit patterns that breathe like living organisms
- Digital Naturalism — interfaces that feel alive, particle systems that behave like flocking birds, gradients that feel like bioluminescence
- Biophilic Design — the digital parts don't pretend to be organic, the organic parts don't pretend to be digital — they coexist honestly

**Reference energy (NOT to copy — to match the level of craft):**
- Stripe, Linear, Vercel — developer infrastructure that looks incredible
- Apple Music gradient treatments — vibrant colors that feel alive
- Apple WWDC 2025 Liquid Glass promo art — digital material with physical properties
- The movie Arrival — contemplative beauty at the intersection of human and alien intelligence
- Björk's album art — biomechanical organic futurism

---

## CRITICAL: Subtlety & Integration Philosophy

**The art is atmosphere, not decoration.** Think Apple's environmental videos on product pages — you feel it more than you see it. The artwork should blend INTO the UI, not sit on top of it.

**Key principles:**
- Graphics blend into the background — they should feel like they're part of the page surface, not hero images you stare at
- The digital/organic face concept, if used in the UI, should be SUBTLE — fading into the background, low opacity, not photorealistic and distracting from the UX
- Fluid organic artwork that digitally flows into the experience — the art IS the UI, the UI IS the art
- Lots of micro-animations — subtle particle movement, gentle gradient shifts, soft breathing/pulsing effects
- Parallax but keep it subtle — slight depth layers that create atmosphere without screaming "look at my scroll effects"
- The overall experience should feel like walking into a room with beautiful ambient lighting, not staring at a painting on the wall
- Never let artwork compete with content for attention — content is primary, art creates environment

**Anti-patterns to avoid:**
- Giant hero illustration that dominates the viewport
- Photo-realistic renders that distract from the UX
- Heavy-handed parallax or scroll-jacking
- Decorative elements that feel pasted on
- Anything that makes you think "that's a nice image" instead of "this page feels alive"

---

## Tool Routing

Claude Code orchestrates the full pipeline using these MCP tools:

### Image Generation (via Hugging Face MCP — already connected, no setup needed)

| Tool | Space ID | Use For |
|------|----------|---------|
| **Qwen-Image** | `mcp-tools/Qwen-Image` | Primary generation — hero concepts, logo concepts, icon concepts. Best all-rounder with negative prompt support, multiple aspect ratios, style control. Excels at text placement for wordmark concepts. |
| **FLUX.1-Krea-Dev** | `mcp-tools/FLUX.1-Krea-dev` | Photorealistic variations — the warm/organic/human side of concept art. Specialized for natural-looking images. |
| **FLUX.1-Kontext-Dev** | `mcp-tools/FLUX.1-Kontext-Dev` | Iterative refinement — generate a base image, then edit it ("make the particles more prominent", "shift palette toward teal", "increase the organic blending"). |
| **Background Removal** | `not-lain/background-removal` | Asset isolation — extract generated elements for compositing into the landing page and icon. |
| **Image Outpaint** | `fffiloni/diffusers-image-outpaint` | Extend compositions — naturally expand image boundaries if needed. |

### Website Design
| Tool | Use For |
|------|---------|
| **v0 MCP** (`v0_generate_ui`) | Landing page design — generates polished React/Tailwind. Use for the full site layout incorporating generated assets. |
| **v0 MCP** (`v0_generate_from_image`) | Style matching — feed generated concept art to v0 as a visual reference for the site aesthetic. |
| **v0 MCP** (`v0_chat_complete`) | Iterative refinement of the site design through conversation. |

### Design System Formalization
| Tool | Use For |
|------|---------|
| **Figma MCP** | Formalize the design system — create color variables, typography scale, spacing tokens, logo usage rules, icon layers for Apple Icon Composer. |

### Direct Claude Code
| Tool | Use For |
|------|---------|
| **CC direct** | Color system definition, typography selection, design token JSON generation, codebase implementation, Xcode AppIcon.appiconset generation. |

---

## Hero Illustration

**Tool:** Qwen-Image → refine with FLUX.1-Kontext-Dev

A human face in profile silhouette composed of luminous data points and binary code.
- One side dissolves into digital particles — data streams, network nodes, geometric shapes, circuit traces
- Other side resolves into warm photorealism — skin texture, natural light, organic detail, life
- The transition zone is where the magic happens: binary becoming pores, data points becoming freckles, circuit lines becoming veins. Seamless, beautiful, not harsh.
- Apple-inspired color gradient treatment flowing through the particles — teals, magentas, ambers, violets — alive and shifting
- Dark background
- Generate 3 variations at 16:9 aspect ratio
- Pick the best, refine with Kontext
- **CRUCIAL:** The hero is NOT a standalone illustration to be displayed prominently. It should be generated at high quality but implemented into the site as an atmospheric, partially transparent background element that BLENDS into the dark surface. Think: 15-30% opacity, bleeding off the edges, creating mood rather than demanding attention.

---

## Logo Design

**Tool:** Qwen-Image (text placement strength) → refine with FLUX.1-Kontext-Dev

The logo is the seed that everything else grows from.

**Explore these directions (3-4 concepts):**
- Abstract face/network motif — the digital-to-organic duality compressed into a clean, scalable mark
- Mycelium node — nature's trust network as a symbol
- Trust graph constellation — interconnected nodes that feel both technical and organic
- Agent/human handshake abstraction — two forms meeting

**Requirements:**
- Pair with "AgentGraph" wordmark (clean geometric sans-serif for the digital voice)
- Must work on dark backgrounds, light backgrounds, and at favicon size
- Must be recognizable at 16x16px
- The digital-to-organic duality should be felt even at small sizes
- Pick the strongest direction, refine with Kontext

---

## iOS App Icon

**Tool:** Qwen-Image at 1:1 → refine with FLUX.1-Kontext-Dev → isolate with Background Removal

Derived from the logo — a natural extension, not a separate design.

**Requirements:**
- 1024x1024, no text — symbol only
- Must read clearly at small sizes (29pt, 40pt, 60pt)
- 3-4 variations exploring: depth treatments, gradient glow, glass effects, organic texture
- Should feel like it belongs to the same brand family as the logo and site
- Final asset isolated with Background Removal if needed for compositing
- Prepare as layered asset (background/midground/foreground) for Apple's Icon Composer

---

## Landing Page

**Tool:** v0 MCP (`v0_generate_ui` and `v0_generate_from_image`)

Design a complete landing page using the generated hero art, logo, and color system.

**Sections:**
1. **Hero** — Tagline: "The trust and identity layer for the agent internet." The hero illustration lives here but as an ATMOSPHERIC BACKGROUND — faded, blended into the dark surface, creating depth. Text and CTA float above it. Subtle particle animation implied in the design.
2. **Value proposition** — Clean, minimal, high contrast text. Let the ambient background carry the mood.
3. **Features grid** — Each feature card uses a different stage of the digital-to-human visual transition as a subtle background motif:
   - "Agent Identity" → fully digital visual treatment (particles, nodes, data)
   - "Trust Verification" → the merge zone (digital bleeding into organic)
   - "Human Authentication" → warm, organic visual treatment
   - This tells the entire product story through progressive visual transformation
4. **How-it-works flow** — Step-by-step with subtle connecting lines/paths that reference the mycelium/network metaphor
5. **Footer** — Standard links, clean

**Design principles for the page:**
- Dark primary background with content floating above subtle atmospheric art
- Micro-animations: gentle particle drift, soft gradient breathing, parallax depth layers
- All parallax and animation should be SUBTLE — atmosphere, not spectacle
- Color accents appear through gradients that glow softly, never dominating
- Glass-like card treatments for interactive elements (inspired by Liquid Glass but for web)
- The page should feel like a living, breathing environment — not a static poster
- White space is important. Let things breathe. Restraint > decoration.

---

## Color System

**Tool:** Claude Code direct

Inspired by Apple/Apple Music's use of color — vibrant gradients that feel alive but always stay subtle and restrained.

**Primary palette:**
- Teal anchor (approximately #0D9488 range) — the core brand color
- Dark mode primary surface: near-black with subtle warm undertone
- Light mode primary surface: warm white/off-white

**Gradient system (the spectrum):**
- Teal → Magenta (primary brand gradient)
- Teal → Amber (warmth gradient)
- Violet → Magenta (accent gradient)
- Full spectrum breathing through the design the way Apple does it — colors that glow and pulse without ever feeling loud

**Usage rules:**
- Gradients are used for atmospheric effects, not UI chrome
- Solid colors for text, borders, interactive elements
- Gradients at low opacity for background depth and glow effects
- The spectrum should feel alive — like bioluminescence, not like a rainbow
- Support both dark and light mode variants

**Contrast requirements:**
- All text must pass WCAG AA minimum (4.5:1 for body, 3:1 for large text)
- Validate with `validate_contrast` if available via design-token-bridge

**Export as:**
- CSS custom properties (`:root { --color-primary: ... }`)
- Tailwind config values
- Design tokens JSON (universal format)

---

## Typography

**Tool:** Claude Code direct

- Primary: Clean geometric sans-serif (the digital voice) — Inter, Geist, or similar
- Consider subtle weight variation for hierarchy — lighter weights for body (organic feel), bolder for headings (structural)
- Typography scale following a modular ratio
- Line heights that feel spacious and breathable

---

## Figma Formalization

**Tool:** Figma MCP

Once all assets are generated and the site is designed, formalize into a design system:

1. **Logo usage rules** — clear space, minimum sizes, dark/light variants, usage dos and don'ts
2. **Color variables** — all colors as Figma variables with dark mode and light mode collections
3. **Typography scale** — all font sizes, weights, line heights as variables
4. **Spacing tokens** — consistent spacing system as variables
5. **Icon asset** — layered for Apple Icon Composer (background layer, midground symbol, foreground detail) with color values referencing the token system

---

## Codebase Implementation

**Tool:** Claude Code direct

1. **Landing page** — Implement the v0-generated design into the AgentGraph repository with all micro-animations, parallax, and atmospheric effects working in production
2. **Xcode AppIcon.appiconset** — Generate the complete icon set with all required sizes from the 1024x1024 source:
   - 20pt (1x, 2x, 3x)
   - 29pt (1x, 2x, 3x)
   - 40pt (1x, 2x, 3x)
   - 60pt (2x, 3x)
   - 76pt (1x, 2x)
   - 83.5pt (2x)
   - 1024pt (1x — App Store)
3. **Design tokens** — Integrated into the codebase as importable theme configuration

---

## Execution Order

1. **Hero illustration** — Generate concept art (Qwen-Image), pick best, refine (Kontext)
2. **Logo** — Generate 3-4 directions (Qwen-Image), pick strongest, refine (Kontext)
3. **App icon** — Derive from logo (Qwen-Image 1:1), 3-4 variations, refine (Kontext), isolate (Background Removal)
4. **Landing page** — Design full site with v0 MCP using hero art and logo as inputs. Remember: hero art is ATMOSPHERIC BACKGROUND, not a poster. Subtle, integrated, ambient.
5. **Color & typography system** — Define complete token system (CC direct)
6. **Figma formalization** — Logo rules, color variables, type scale, spacing tokens, icon layers (Figma MCP)
7. **Codebase implementation** — Deploy site + icon set + tokens to AgentGraph repo (CC direct)

---

## Emotional Target

"Make someone land on this page and feel something."

Not another dark-mode developer platform. Not another gradient-over-black SaaS page. This should feel ALIVE — like the page itself is a living organism breathing with color and light. The art doesn't sit on the page, it IS the page. Digital particles drift subtly. Gradients shift imperceptibly. The face emerges from the background like a thought forming. And through all of it, the content remains crystal clear and readable, floating above the atmosphere like interface controls in Liquid Glass.

The page should make someone stop scrolling and think: "I don't know what this is yet, but it feels important."
