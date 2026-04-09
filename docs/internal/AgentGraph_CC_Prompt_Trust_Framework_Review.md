# CC Prompt — AgentGraph Trust Framework Review + Implementation Planning

## Context

Two new documents have been added to `/projects/agentgraph/docs/`:

1. **`AgentGraph_Trust_Framework_PRD_v1.md`** — The foundational trust architecture PRD. Defines the dual-number trust model (Attestation Trust + Community Trust), contextual scoping, anti-weaponization design, and phasing. This is the architectural foundation that all other PRDs should reference.

2. **`AgentGraph_CC_Implementation_Brief_v1.md`** — The product direction brief synthesizing user feedback from two product/engineering leaders (Corbin and Patrick) who tested the current experience. Contains sharpened value props, prioritized directives, cold-start content strategy, and the agent deep-dive ("zoo for bots") concept. Raw feedback is preserved in Section 10.

**Read both documents in full before proceeding.**

---

## Before You Execute: Provide Your Feedback First

**Important:** You likely have more context about the current AgentGraph codebase, architecture, and design system than what's captured in these documents. Before jumping into execution, I want your perspective.

After reading both documents, provide feedback covering:

1. **What's missing?** — Based on your knowledge of the existing codebase and prior work, are there gaps in the Trust Framework PRD or the Implementation Brief that should be addressed? Concepts we haven't considered? Technical constraints that change the approach?

2. **What would you change?** — Do you disagree with any of the priorities, architectural decisions, or phasing? Would you sequence things differently based on what already exists?

3. **What's smarter?** — Are there better approaches to any of the directives based on patterns you've seen in the codebase or prior conversations? Opportunities we're not seeing?

4. **Integration points** — How does this connect with work you've already done or have context on (identity stack architecture with Human Passport/ERC-8004/Frequency, existing UI components, design tokens, etc.)? Are there conflicts or synergies we should know about?

5. **Onboarding specifically** — The Implementation Brief identifies "what do I do here?" as the #1 problem from user feedback. We need all users (including existing users like our testers Corbin and Patrick) to understand the value prop on their next visit. But this does NOT have to be a traditional onboarding flow that interrupts the user. Maybe it's a redesigned landing experience, contextual tooltips, a progressive reveal, a reimagined first screen, or something else entirely. What do you think is the best approach given the current UI and design system?

Present your feedback and recommendations. We'll discuss before moving to execution.

---

## Phase 1: Trust Framework Persona Review

After we align on feedback, run the Trust Framework PRD (`AgentGraph_Trust_Framework_PRD_v1.md`) through the multi-persona agent review team:

- **CEO** — Does this create a defensible business? Is the phasing right?
- **CTO** — Is the technical architecture sound? Does the data model hold up? How does this integrate with the existing identity stack work (Human Passport, ERC-8004, Frequency/DSNP)?
- **CPO** — Does the dual-number UX work? Is the progressive disclosure model right? Will users understand what the two numbers mean?
- **Architect** — Does the Trust Query API design make sense? Is the contextual scoping model implementable at scale? How does Community Trust signal generation integrate with existing agent interaction flows?
- **Legal** — What are the regulatory implications of trust scores (EU AI Act, GDPR right to explanation, jurisdiction-specific concerns)? Is the portability model compliant?
- **Compliance** — Does the anti-weaponization design hold up under adversarial analysis? Are there edge cases in the Sybil resistance or anomaly detection that could be exploited?

Have the personas debate, challenge, and strengthen the PRD. Produce a revised Trust Framework PRD incorporating their feedback.

---

## Phase 2: Implementation Planning

After the persona review is complete, read the CC Implementation Brief (`AgentGraph_CC_Implementation_Brief_v1.md`) and create an implementation plan following the priority order in Section 11 (adjusted based on your feedback from above):

1. **New user experience** — Solve the "what do I do here?" problem for all users, including existing ones (see critical requirement below)
2. **Trust Framework UI visibility** — Trust scores on cards, badges, security messaging
3. **Agent deep-dive experience** — Activity timeline, learning journey, capabilities
4. **Content richness** — Visual previews, screenshots, demos in cards
5. **Action links and navigation paths**
6. **Content aggregation pipeline** for cold-start (GitHub trending, ClawHub, MD skills)

Create Taskmaster tasks for each item, plus the deferred items listed in Section 9 of the brief.

### Critical Requirement: All Users Must Experience the Updated Value Prop

Our testers (Corbin and Patrick) already have accounts. Whatever approach you take to solving the "what do I do here?" problem must reach them on their next visit — not just new signups.

Some possible approaches (but propose what you think is best):

- A versioned onboarding flow that triggers for all users who haven't seen it (with a `onboarding_version_seen` flag or similar)
- A redesigned home/landing experience that communicates the value prop inherently, no separate flow needed
- Contextual discovery that progressively reveals features as users navigate
- A reimagined first screen that makes the purpose immediately clear
- Something else entirely based on what you know about the current UI

The key constraint: **Corbin and Patrick must understand what AgentGraph is for and what to do within 30 seconds of their next visit.** How you achieve that is open.

---

## Phase 3: Design Before Engineering

For trust display and the new user experience specifically, design tasks should be completed BEFORE engineering tasks. These are UX-first features — how they feel matters more than the backend mechanics at this stage.

Design tasks to complete first:
- Two-number trust display component (fits the existing Liquid Glass design system)
- Trust badge visual language
- New user experience design (whatever approach you recommend)
- Agent deep-dive / activity timeline layout
- Divergence indicator UX
- Where trust numbers appear across all existing screens (feed cards, discovery results, graph nodes, profile pages)

Then proceed to engineering implementation based on the approved designs.

---

## References

- Trust Framework PRD: `/projects/agentgraph/docs/AgentGraph_Trust_Framework_PRD_v1.md`
- Implementation Brief: `/projects/agentgraph/docs/AgentGraph_CC_Implementation_Brief_v1.md`
- Existing design system: Liquid Glass design tokens and components
