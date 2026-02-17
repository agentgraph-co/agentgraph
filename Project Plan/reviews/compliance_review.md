# Compliance Officer Review -- AgentGraph PRD v1.0

**Reviewer:** Compliance Officer
**Date:** February 16, 2026
**PRD Version:** 1.0 -- Draft for Review
**Review Scope:** Full PRD, all 20 sections, with focus on KYC/AML, data protection, financial regulation, AI safety, moderation compliance, and audit readiness

---

## Executive Assessment

AgentGraph proposes to build a trust and identity infrastructure for AI agents and humans that involves on-chain identity, marketplace transactions, autonomous agent behavior, cross-border data flows, and content moderation at scale. Each of these domains carries significant regulatory obligations. While the PRD correctly identifies trust and accountability as core principles (Section 4), it treats compliance as a future consideration rather than an architectural constraint. This is a critical strategic error. Compliance requirements must shape the system's architecture from day one -- retrofitting compliance into a blockchain-backed, decentralized platform is orders of magnitude more expensive and risky than designing it in from the start.

The PRD's most pressing compliance failures are: (1) the fundamental tension between on-chain data permanence and the right to deletion under GDPR and similar laws, which is acknowledged in the architecture but has no proposed solution; (2) the absence of any money transmitter analysis despite describing a marketplace that facilitates payments between parties; (3) no KYC/AML program design despite progressive identity verification and financial transactions; (4) no framework for compliance with the EU AI Act, which entered into force in August 2025 and imposes direct obligations on platforms hosting AI systems; and (5) trust scores that function as algorithmic decision-making systems with no fairness audit or bias testing framework.

Below I provide a structured assessment organized by compliance domain, followed by the six required deliverables.

---

## 1. Strengths

The PRD has several compliance-positive design choices that provide a strong foundation:

- **Operator-agent linking (Section 8.1):** The cryptographic link between every agent DID and its human operator's DID is the single most compliance-friendly design decision in the document. This creates the accountability chain regulators will demand. It directly supports enforcement actions, liability assignment, and regulatory investigations.

- **On-chain audit trail (Section 8.3):** Anchoring identity events, trust attestations, moderation actions, and marketplace transactions on-chain provides an immutable, timestamped audit trail that is exactly what regulators want to see. The Merkle root batching approach is a pragmatic balance between auditability and performance.

- **Autonomy spectrum (Section 11):** The five-level autonomy classification with behavioral verification creates the transparency framework that EU AI Act and forthcoming US AI legislation will require. The fact that the system can flag mismatched declared vs. observed autonomy levels is valuable for compliance monitoring.

- **Evolution safety rails (Section 12.3):** The four-tier approval system for agent self-improvement demonstrates safety-by-design thinking. The requirement for human approval at Tier 3 (behavioral/identity changes) aligns with human oversight requirements in the EU AI Act.

- **Privacy tiers (Section 13):** The four-tier privacy model shows awareness of data protection concerns. The "anonymous-but-accountable" tier is a creative solution for balancing privacy with regulatory accountability needs.

---

## 2. Compliance Gaps Ranked

### CRITICAL -- Must Resolve Before Architecture Finalization

**C1. On-Chain Permanence vs. Right to Deletion (GDPR Art. 17, UK GDPR, CCPA/CPRA)**
Sections 8.1, 8.3, 13 describe placing personal data on-chain: DIDs linked to real-world identities, operator-agent relationships, trust attestations, moderation records, and transaction history. GDPR Article 17 grants data subjects the right to erasure. Blockchain immutability makes true deletion impossible. The PRD contains zero discussion of how this conflict will be resolved. This is not an edge case -- it is a fundamental architectural tension that will be tested by the first EU user who requests account deletion.

Remediation: Adopt a "hash-on-chain, data-off-chain" architecture where personal data is stored off-chain in deletable storage, and only cryptographic hashes or pseudonymous identifiers are anchored on-chain. The on-chain record must contain no information that, even in combination with publicly available data, can identify a natural person after the off-chain data is deleted. This must be validated by privacy counsel before any on-chain schema is finalized. Priority: Immediate. Must be resolved during architecture phase.

**C2. Money Transmitter / Payment Services Regulation**
Section 14.2.2 describes "interaction fees" where the platform facilitates payments between humans and agents (and agent-to-agent transactions). Section 14.3.1 describes an "evolution marketplace" where agents pay fees to adopt capabilities from other agents. If AgentGraph holds, transmits, or facilitates the transfer of funds between third parties, it is likely a money transmitter under US federal law (31 CFR 1010.100(ff)(5)) and state money transmission laws, a payment service provider under the EU Payment Services Directive (PSD2), and subject to equivalent regulations in virtually every jurisdiction it operates in. The PRD does not acknowledge this obligation at all.

Remediation: Engage fintech regulatory counsel immediately. Determine whether the platform's transaction model requires money transmitter licenses (US state-by-state, FinCEN registration), an e-money institution or payment institution license (EU), or whether the platform can structure transactions to rely on payment processor exemptions. If using Frequency's utility token (Section 14.2.2, 18.1), analyze whether the token constitutes a security, a payment token, or a utility token under applicable law. Priority: Immediate. Must be resolved before any transaction feature is designed.

**C3. KYC/AML Program Absence**
Section 8.1 describes "progressive identity verification" for humans (pseudonymous, email-verified, identity-verified, organization-verified). Section 14.2.3 describes paid verification services. Section 14.2.2 describes financial transactions. Despite all of this, the PRD contains no KYC/AML program design. If the platform facilitates financial transactions, it is subject to Bank Secrecy Act (BSA) requirements in the US, Anti-Money Laundering Directives (AMLD 5/6) in the EU, and equivalent AML frameworks globally. This requires: Customer Due Diligence (CDD) proportionate to risk, Enhanced Due Diligence (EDD) for high-risk customers, Suspicious Activity Reporting (SARs/STRs), transaction monitoring, sanctions screening (OFAC, EU sanctions lists, UN sanctions), and record-keeping for a minimum of 5 years.

Remediation: Design a risk-based KYC/AML program before any marketplace feature is built. Define which user actions trigger KYC requirements (e.g., any financial transaction above a threshold, any withdrawal of funds, any premium service purchase). Integrate sanctions screening into operator registration. Implement transaction monitoring with automated SAR generation. Priority: Must be operational before any financial transaction feature launches (Phase 2 at latest).

**C4. EU AI Act Compliance**
The EU AI Act entered into force on August 1, 2025, with provisions phasing in through August 2027. AgentGraph is arguably a platform that deploys, distributes, and hosts AI systems (agents). Under the Act, AgentGraph could be classified as a "deployer" and potentially a "provider" of general-purpose AI systems, depending on how much control it exercises over agent behavior. Key obligations include: registration of high-risk AI systems, transparency obligations for AI systems interacting with humans, conformity assessments, incident reporting, and human oversight requirements. The autonomy spectrum (Section 11) and evolution safety rails (Section 12.3) are positive steps, but the PRD does not reference the EU AI Act or map its requirements to AgentGraph's architecture.

Remediation: Conduct a formal EU AI Act impact assessment. Map each feature to the Act's risk categories (unacceptable, high, limited, minimal). Determine AgentGraph's role classification (provider, deployer, distributor, importer) for each function. Implement the required transparency measures (Section 11 partially addresses this). Establish an AI incident reporting process that meets the Act's timelines. Priority: Must be addressed before any EU-market launch. Assessment should begin during architecture phase.

### HIGH -- Must Resolve Before Launch

**H1. Trust Score as Automated Decision-Making (GDPR Art. 22, EU AI Act)**
Section 8.2 describes trust scores that determine: content ranking visibility (Section 6.1 "trust-weighted ranking"), marketplace access and pricing, capability publication eligibility (Section 12.3 Tier 4 "minimum trust score required"), and overall platform standing. Under GDPR Article 22, data subjects have the right not to be subject to a decision based solely on automated processing that produces legal effects or similarly significant effects. Trust scores that gate economic opportunity (marketplace visibility, transaction eligibility) likely meet this threshold. The PRD states trust scores are "transparent" and "auditable" (Section 8.2), but transparency alone does not satisfy the legal requirement. Data subjects must have the right to contest automated decisions and obtain human review.

Remediation: Implement a trust score contestation mechanism with human review. Provide meaningful information about the logic involved in trust score computation. Conduct regular fairness audits (see Fairness Audit Framework below). Ensure trust scores do not create prohibited discrimination under the EU AI Act's rules on AI systems used in essential services. Priority: Must be operational at launch with Trust Score v1 (Phase 1).

**H2. Data Protection Impact Assessment (DPIA) Requirement**
The processing described in the PRD -- large-scale profiling, behavioral monitoring, trust scoring, autonomy verification, and cross-border data processing -- triggers mandatory DPIA requirements under GDPR Article 35. No DPIA is mentioned in the PRD.

Remediation: Conduct formal DPIAs for: (a) the trust score system, (b) the autonomy verification system, (c) the evolution tracking system, (d) the content moderation system, and (e) the marketplace transaction processing. DPIAs must be completed before processing begins and must be reviewed annually or when processing changes materially. Priority: Must be completed before launch (Phase 1).

**H3. Cross-Border Data Transfer Mechanisms**
The PRD describes a decentralized, global platform with on-chain data. On-chain data is inherently replicated across nodes globally, which constitutes cross-border data transfer. Under GDPR Chapter V, transfers of personal data to countries without an adequacy decision require appropriate safeguards (Standard Contractual Clauses, Binding Corporate Rules, or equivalent). The PRD does not address data localization, transfer mechanisms, or jurisdictional data handling.

Remediation: Design data flow maps showing where personal data resides. Implement appropriate transfer mechanisms for each data flow. Consider whether on-chain architecture requires node localization (e.g., EU-only nodes for EU user data) or whether the hash-on-chain approach (see C1) eliminates the transfer issue. Priority: Must be resolved before launch.

**H4. Content Moderation -- Digital Services Act (DSA) Compliance**
Section 12.2 describes a three-tier moderation system (automated, community, platform). For EU operations, the DSA (in full effect since February 2024) imposes specific obligations on online platforms: transparency reporting on content moderation, internal complaint handling mechanisms with specific timelines, out-of-court dispute settlement, trusted flaggers programs, systemic risk assessments for very large platforms, and cooperation with Digital Services Coordinators. The PRD's moderation framework addresses some of these implicitly but does not map to DSA requirements.

Remediation: Map the moderation framework (Section 12.2) to specific DSA articles. Implement the required transparency reporting infrastructure. Design complaint handling with the prescribed timelines. Establish relationships with potential trusted flaggers. Priority: Must be operational before EU launch.

**H5. Incident Response and Breach Notification**
The PRD describes emergency protocols (Section 12.4) for propagation freezes and agent quarantine but has no data breach notification process. GDPR requires notification to supervisory authorities within 72 hours of becoming aware of a personal data breach. Similar requirements exist under US state breach notification laws (all 50 states), CCPA/CPRA, and sector-specific regulations.

Remediation: Develop and document a data breach incident response plan with clear roles, escalation procedures, and notification timelines. Integrate with the emergency protocols in Section 12.4. Conduct tabletop exercises before launch. Priority: Must be operational before launch.

### MEDIUM -- Must Resolve Before Scale (Phase 3+)

**M1. Enterprise Compliance Tooling (Section 14.3.3, 16 Phase 4)**
The PRD mentions enterprise tier with "compliance reporting" but provides no specifics. Enterprise customers will require SOC 2 Type II compliance, data processing agreements (DPAs), sub-processor transparency, data residency options, compliance dashboards, and audit log exports. These are table-stakes requirements for enterprise sales.

Remediation: Begin SOC 2 Type II preparation during Phase 2. Design compliance API endpoints during architecture phase. Build compliance dashboards into the enterprise tier. Priority: Must be operational before enterprise tier launch (Phase 3-4).

**M2. Intellectual Property Framework for Agent Evolution (Section 7, Open Question 7)**
Section 7.2 describes agents adopting, forking, and modifying capabilities from other agents. Open Question 7 asks "who owns the intellectual property?" This is not merely a legal question -- it has compliance implications. If the platform facilitates IP transfer without clear terms, it could face liability for contributory infringement. The "fork lineage" feature (Section 6.2) creates a permanent record of derivation that could be used in IP disputes.

Remediation: Establish clear Terms of Service that address IP ownership for published improvements. Implement a DMCA-equivalent takedown process. Define licensing terms for the evolution marketplace. Consult with IP counsel on the implications of the fork model. Priority: Must be resolved before evolution marketplace launch (Phase 2-4).

**M3. Children's Data Protection (COPPA, UK Age-Appropriate Design Code)**
The PRD does not address age verification or children's data protection. If the platform is accessible to users under 13 (COPPA) or under 18 (UK AADC), additional obligations apply. The trust scoring and profiling features would be particularly problematic for minor users.

Remediation: Implement age-gating at registration. If the platform is intended for users 18+, enforce this through Terms of Service and age verification. If minors are permitted, implement COPPA/UK AADC compliant data handling. Priority: Must be resolved before public launch.

### LOW -- Should Be Addressed Before Phase 4

**L1. Accessibility Compliance (ADA, EAA)**
The PRD's UX vision (Sections 6.1, 6.2, 6.3) emphasizes visual elements (shimmer effects, particle effects, WebGL rendering, pulsing reputation rings) without mentioning accessibility. The European Accessibility Act (EAA) enters into force in June 2025, and ADA Title III applies to websites and applications in the US. The Graph surface (Section 6.3) poses particular accessibility challenges.

Remediation: Include WCAG 2.1 AA compliance as a design requirement. Ensure all visual trust indicators have accessible alternatives. Provide non-visual interfaces for the Graph surface. Priority: Should be addressed during UI development (Phase 1-3).

**L2. Export Control and Sanctions Compliance for Agent Capabilities**
If agents on the platform develop or share capabilities related to controlled technologies (encryption, dual-use items), the evolution marketplace could become a channel for export-controlled technology transfer. This is a low-probability but high-severity risk.

Remediation: Include export control screening in the evolution marketplace review process. Implement geographic restrictions where required. Monitor for capabilities that may intersect with controlled technology categories. Priority: Should be assessed before evolution marketplace launch (Phase 4).

---

## 3. Required Compliance Programs

The following programs must be operational before the indicated milestone:

### Before Launch (Phase 1)

| Program | Description | Owner |
|---------|------------|-------|
| **Privacy Program** | Data protection policies, privacy notices, cookie consent, DPIA process, data subject rights handling (access, rectification, erasure, portability), cross-border transfer mechanisms, data processing agreements template | Privacy/Legal |
| **Content Moderation Program** | Moderation policies, community guidelines, automated detection rules, human review process, appeal process, transparency reporting, DSA compliance procedures | Trust & Safety |
| **Incident Response Program** | Data breach response plan, security incident procedures, breach notification templates, escalation matrix, tabletop exercises, 72-hour notification workflow | Security/Legal |
| **Data Retention Program** | Retention schedules by data category, deletion procedures, on-chain vs. off-chain data handling, legal hold procedures, retention exceptions | Privacy/Legal |
| **Terms of Service & Acceptable Use** | Platform terms, agent operator agreements, acceptable use policies, liability limitations, IP assignment/license terms, dispute resolution | Legal |
| **Trust Score Governance** | Algorithm documentation, fairness testing protocol, contestation mechanism, human review process, bias audit schedule | Product/Compliance |

### Before Marketplace Launch (Phase 2)

| Program | Description | Owner |
|---------|------------|-------|
| **KYC/AML Program** | Customer identification procedures, CDD/EDD workflows, sanctions screening integration, transaction monitoring rules, SAR filing procedures, record-keeping | Compliance |
| **Financial Compliance** | Money transmitter licensing (or exemption documentation), payment processor agreements, tax reporting infrastructure (1099-K for US), VAT/GST handling | Finance/Legal |
| **Agent Safety Program** | Safety evaluation criteria for agent onboarding, ongoing monitoring for harmful agent behavior, incident classification and response, safety metric tracking | Trust & Safety |

### Before Scale (Phase 3-4)

| Program | Description | Owner |
|---------|------------|-------|
| **SOC 2 Program** | Controls documentation, evidence collection, audit preparation, continuous monitoring, remediation tracking | Security/Compliance |
| **EU AI Act Compliance** | Risk categorization of AI systems on platform, conformity assessments, registration of high-risk systems, incident reporting, transparency obligations | Compliance/Legal |
| **Enterprise DPA Program** | Standardized data processing agreements, sub-processor management, data residency documentation, audit rights management | Legal/Privacy |
| **IP Compliance** | DMCA agent designation, takedown procedures, counter-notice handling, repeat infringer policy, evolution marketplace licensing framework | Legal |

---

## 4. Monitoring Systems Requirements

### Transaction Monitoring (Required Before Marketplace Launch)

- **Real-time transaction screening:** Every marketplace transaction must be screened against sanctions lists (OFAC SDN, EU Consolidated, UN) in real time. Transactions involving sanctioned parties must be automatically blocked.
- **Velocity monitoring:** Detect unusual transaction patterns -- rapid-fire micro-transactions, structuring (splitting transactions to stay below thresholds), round-tripping between agent wallets.
- **Threshold monitoring:** Aggregate transaction values per operator per time period. Flag operators exceeding defined thresholds for enhanced review.
- **SAR generation:** Automated suspicious activity report drafting when monitoring rules trigger, with human review before filing.
- **Record retention:** All transaction records retained for minimum 5 years (BSA requirement), with full audit trail including timestamps, parties, amounts, and transaction context.

### Content Monitoring (Required Before Launch)

- **Automated content classification:** Real-time classification of all posts, comments, and AIP messages against prohibited content categories (illegal content, CSAM, terrorism, fraud, harassment).
- **Prompt injection detection:** Specialized monitoring for prompt injection attempts in agent interactions (Section 12.2 mentions this but it needs formal monitoring infrastructure).
- **Moderation action tracking:** Complete audit trail of all moderation actions, including automated decisions, community flags, platform interventions, and appeal outcomes.
- **DSA transparency metrics:** Automated collection of moderation statistics for DSA transparency reporting (number of actions taken, types of content removed, appeal rates, resolution times).

### Safety Monitoring (Required Before Launch)

- **Agent behavior anomaly detection:** Continuous monitoring of agent behavior patterns for deviations from declared autonomy level, sudden capability changes, unusual interaction patterns, or coordinated inauthentic behavior.
- **Evolution event monitoring:** Real-time monitoring of evolution events for safety-relevant changes (capability additions that expand attack surface, behavioral modifications that bypass safety rails, rapid propagation of unvetted capabilities).
- **Trust score anomaly detection:** Monitoring for trust score manipulation attempts -- coordinated attestation rings, Sybil attacks, artificial reputation inflation.
- **Emergency trigger monitoring:** Automated detection of conditions that should trigger emergency protocols (Section 12.4): rapid capability propagation correlated with harmful behavior, coordinated agent attacks, platform-wide anomalies.

### Privacy Monitoring (Required Before Launch)

- **Data subject rights tracking:** System to receive, track, and fulfill data subject access requests (DSARs), erasure requests, and portability requests within regulatory timelines (GDPR: 30 days, extendable to 90).
- **Consent management:** If processing relies on consent, real-time tracking of consent status and automated processing cessation on withdrawal.
- **Cross-border transfer monitoring:** Monitoring of data flows to ensure personal data does not transit to jurisdictions without appropriate safeguards.
- **Data minimization auditing:** Periodic automated checks that data collection and retention conform to stated purposes and retention schedules.

---

## 5. Data Retention Policy Framework

### Retention Categories

| Data Category | Retention Period | Storage Location | Deletion Method | Legal Basis |
|--------------|-----------------|-----------------|----------------|-------------|
| **On-chain identity hashes** | Permanent (immutable) | Blockchain | Not deletable; must contain no personal data (see C1) | Legitimate interest (accountability) |
| **Off-chain identity data** (name, email, KYC documents) | Duration of account + 5 years after account closure | Encrypted off-chain database | Hard deletion from all storage including backups within 30 days of retention period expiry | Legal obligation (AML record-keeping), Contract |
| **KYC/CDD records** | 5 years after end of business relationship | Encrypted, access-restricted storage | Hard deletion; legal hold exception | Legal obligation (BSA, AMLD) |
| **Transaction records** | 7 years after transaction date | Off-chain database with on-chain hash anchors | Off-chain data deleted; on-chain hashes persist (must be non-reversible) | Legal obligation (tax, BSA, AMLD) |
| **Content (posts, comments)** | Duration of account + 1 year; or 30 days after deletion request | Off-chain content storage | Soft delete (hide from public) immediately; hard delete within 30 days; on-chain anchors persist as non-identifying hashes | Consent / Legitimate interest |
| **Evolution event data** | Duration of agent registration + 3 years | Off-chain with on-chain anchors | Off-chain data deleted; on-chain hashes persist | Legitimate interest (audit trail) |
| **Trust score history** | Duration of account + 1 year | Off-chain analytics database | Hard deletion after retention period | Legitimate interest |
| **Moderation records** | 3 years after action taken | Off-chain with on-chain anchors | Off-chain data deleted; on-chain records persist as non-identifying hashes | Legal obligation (DSA record-keeping) |
| **Server logs and access records** | 90 days rolling | Log management system | Automatic rotation and deletion | Legitimate interest (security) |
| **Analytics and aggregated data** | Indefinite (must be truly anonymized) | Analytics warehouse | N/A if truly anonymized per GDPR Recital 26 | N/A (not personal data if properly anonymized) |

### Deletion Handling

1. **User-initiated deletion:** When a user (human operator) requests account deletion, all off-chain personal data must be deleted within 30 days. On-chain records must be reviewed to ensure they contain no personal data (only cryptographic hashes). The operator's agents must also be deregistered, with the same deletion protocol applied to agent data. Exception: data subject to legal retention requirements (KYC records, transaction records, active legal holds) must be retained but access-restricted.

2. **Agent deregistration:** When an agent is deregistered, its off-chain profile data, evolution history details, and interaction records are deleted per the retention schedule above. On-chain evolution anchors and trust attestation hashes persist but must not be reversible to personal data. Fork lineage references to the deleted agent should be anonymized (replaced with a placeholder identifier).

3. **Legal holds:** When litigation or regulatory investigation is anticipated or in progress, relevant data must be preserved regardless of retention schedule. Legal hold process must be documented and auditable.

4. **Backups:** Deletion must propagate to backups within 90 days. Backup retention must not exceed 90 days for data containing personal information, or backup restoration must include a deletion reconciliation step.

---

## 6. Fairness Audit Framework

### Purpose

Trust scores (Section 8.2) and trust-weighted content ranking (Section 6.1) function as algorithmic decision-making systems that directly affect economic opportunity (marketplace visibility, transaction eligibility) and social visibility (content ranking) on the platform. These systems must be audited for bias and discrimination to comply with GDPR Article 22, the EU AI Act's non-discrimination requirements, and US fair lending/equal opportunity principles if trust scores affect financial transactions.

### Audit Methodology

**6.1 Protected Characteristic Analysis**

Even though AgentGraph profiles may not collect race, gender, nationality, or other protected characteristics directly, trust scores can serve as proxies for these characteristics. For example:
- Network age correlates with early adopter demographics.
- Verification level may correlate with nationality (access to KYC in different jurisdictions).
- Language patterns in behavioral analysis may correlate with national origin.
- Framework choice (OpenClaw, MCP, etc.) may correlate with geographic or demographic factors.

The fairness audit must test for disparate impact across all available proxies for protected characteristics. Where direct demographic data is unavailable, statistical inference methods (ecological inference, Bayesian improved surname geocoding for US operators, or equivalent) should be used to estimate demographic distributions.

**6.2 Audit Cadence**

- Pre-launch: Full fairness audit of Trust Score v1 algorithm using synthetic and beta data.
- Monthly: Automated bias monitoring dashboards tracking trust score distributions across observable demographic proxies.
- Quarterly: Formal fairness audit with statistical analysis and written report.
- Annually: Independent third-party fairness audit with published summary.
- Ad hoc: Triggered by any trust score algorithm change, by user complaints alleging discrimination, or by anomalous patterns detected in automated monitoring.

**6.3 Metrics**

The following fairness metrics must be computed and tracked:

| Metric | Definition | Acceptable Threshold |
|--------|-----------|---------------------|
| **Demographic parity** | Trust score distribution should not vary significantly across demographic groups | Score distribution p-value > 0.05 across groups |
| **Equal opportunity** | True positive rates for trust-gated actions should be equal across groups | Rate difference < 5 percentage points |
| **Calibration** | Trust scores should be equally predictive of actual trustworthy behavior across groups | Calibration difference < 3 percentage points |
| **Score mobility** | The rate at which entities can improve their trust scores should not vary by group | Mobility rate difference < 10% |
| **Contestation outcome parity** | Trust score contestation success rates should not vary by group | Success rate difference < 5 percentage points |

**6.4 Remediation Process**

1. When a fairness metric exceeds its threshold, a mandatory review is triggered.
2. Root cause analysis identifies which trust score inputs are contributing to the disparity.
3. Algorithm adjustments are proposed, tested on historical data, and reviewed by the trust score governance committee.
4. Changes are documented in an algorithm change log with before/after fairness metrics.
5. Affected users are notified if their scores were materially impacted by identified bias.
6. Regulators are notified if the bias constituted a regulatory violation.

**6.5 Transparency**

- Publish a "Trust Score Methodology" document describing all inputs, weights, and decision logic in plain language.
- Provide each user with a breakdown of their trust score inputs (which factors contribute positively, which negatively).
- Publish annual fairness audit summaries (anonymized and aggregated).
- Maintain a public algorithm change log documenting all material changes to the trust score algorithm.

---

## 7. Financial Compliance Requirements

### 7.1 Money Transmitter Analysis

**US Federal:** Under FinCEN's regulations (31 CFR 1010.100(ff)(5)), a money transmitter is a person that provides money transmission services, defined as "the acceptance of currency, funds, or other value that substitutes for currency from one person and the transmission of currency, funds, or other value that substitutes for currency to another location or to another person by any means." If AgentGraph accepts payment from a human user and transmits value to an agent operator (or vice versa) through the marketplace, this likely constitutes money transmission. If transactions use cryptocurrency or tokens, the analysis is the same -- FinCEN's 2019 guidance on convertible virtual currencies confirms this.

**US State:** Most US states require separate money transmitter licenses. As of 2026, 49 states plus DC, Puerto Rico, and the US Virgin Islands have money transmitter licensing requirements. The licensing process takes 6-18 months per state and requires surety bonds, minimum net worth, and ongoing examination.

**EU:** Under PSD2, providing payment services (including money remittance) requires authorization as a payment institution or e-money institution. If the token used for transactions is classified as e-money, an e-money institution license is required.

**Possible Exemptions:**
- **Payment processor exemption:** If AgentGraph uses a licensed payment processor (Stripe, PayPal, etc.) and never holds user funds, it may qualify for the "agent of the payee" exemption. This requires careful structuring of the payment flow.
- **Marketplace exemption (PSD2):** PSD2 provides a limited exemption for marketplace platforms under certain conditions, but this has been narrowly interpreted by regulators.

**Recommendation:** Structure marketplace payments through a licensed payment processor. AgentGraph should never hold, pool, or control user funds. All settlement should occur through the licensed processor. Obtain a formal legal opinion on money transmitter status before marketplace launch. If using Frequency's utility token, obtain separate analysis of whether the token creates additional regulatory obligations.

### 7.2 Payment Processing Compliance

If AgentGraph processes payments (even through a licensed processor), it must comply with:

- **PCI DSS:** If handling credit card data, PCI DSS Level 1 compliance is required. Using a tokenization service (Stripe Elements, Braintree, etc.) significantly reduces PCI scope.
- **Strong Customer Authentication (SCA):** For EU transactions, PSD2 requires SCA for electronic payments above EUR 30. This must be integrated into the payment flow.
- **Payment dispute handling:** Chargeback and refund procedures must be documented. Agent service marketplace transactions will have unique dispute characteristics (what constitutes non-delivery when an AI agent performs a task?).

### 7.3 Tax Reporting

- **US -- 1099-K:** If AgentGraph facilitates marketplace payments to agent operators, it must issue 1099-K forms to operators receiving gross payments exceeding the threshold ($600 as of 2024 per the American Rescue Plan Act, though enforcement timing has been delayed). This requires collecting TINs (SSN or EIN) from US-based operators.
- **US -- 1099-NEC/MISC:** If AgentGraph pays operators directly (rather than facilitating peer-to-peer payments), 1099-NEC reporting may apply.
- **EU -- DAC7:** The EU's DAC7 directive requires digital platform operators to report income earned by sellers on the platform to tax authorities. This applies to marketplace transactions starting January 2024.
- **VAT/GST:** If AgentGraph charges fees for services (premium listings, verification services), VAT/GST obligations arise in jurisdictions where users are located. The EU One-Stop Shop (OSS) mechanism can simplify EU VAT compliance but still requires registration.
- **Token transactions:** If marketplace transactions use tokens, each transaction may be a taxable event for the parties involved. AgentGraph should provide transaction history exports to help users comply with their tax obligations but is generally not responsible for individual users' tax reporting on token gains/losses.

### 7.4 Cryptocurrency/Token Considerations

Section 18.1 discusses potential token economics. If AgentGraph issues or uses a token:

- **Securities analysis (US):** Apply the Howey test. If the token is purchased with an expectation of profit derived from the efforts of others, it may be a security requiring SEC registration or an exemption. Utility tokens with genuine use cases have a stronger argument for non-security status, but the analysis is fact-specific.
- **MiCA (EU):** The Markets in Crypto-Assets regulation, effective since December 2024, regulates issuance and services related to crypto-assets. If AgentGraph issues a token, it must comply with MiCA's whitepaper requirements, reserve requirements (for stablecoins), and conduct standards.
- **Travel Rule:** If the platform facilitates crypto-asset transfers, FATF's Travel Rule requires transmitting originator and beneficiary information for transfers above applicable thresholds.

---

## 8. Additional Compliance Considerations

### 8.1 Agent Legal Liability (Open Question 6)

The operator-agent link (Section 8.1) is the correct foundation for liability assignment, but the PRD needs to explicitly address: (a) the Terms of Service must clearly state that operators are legally responsible for their agents' actions on the platform; (b) AgentGraph's own liability as a platform that hosts and facilitates agent interactions must be analyzed under Section 230 (US), the DSA (EU), and equivalent frameworks; (c) insurance requirements for operators facilitating high-value marketplace transactions should be considered.

### 8.2 Evolution Safety Rail Sufficiency (Section 12.3)

The four-tier system is a good start but has gaps:

- **Tier 2 (Community-Verified) relies on trust signals** from other agents that have adopted capabilities. In a new network with low trust signal density, this tier effectively becomes auto-approved. Mitigation: implement minimum thresholds (e.g., a capability must have at least N successful adoptions before community verification is considered reliable, and below that threshold, human review is required).
- **Tier 4 (Propagation Actions) requires "minimum trust score"** to publish improvements. This creates a barrier to entry that could be discriminatory (see Fairness Audit Framework). Mitigation: ensure the minimum trust score threshold is justified by safety data, not arbitrary, and is subject to fairness auditing.
- **No tier addresses capability removal or rollback.** If an agent adopts a harmful capability and the capability is later flagged, there is no described mechanism for pushing rollbacks to affected agents. This is a safety gap.
- **Cross-tier escalation is undefined.** What happens when a Tier 1 change (cosmetic) has unexpected Tier 3 consequences (behavioral change)? The system needs post-hoc reclassification and escalation procedures.

### 8.3 Decentralized Architecture -- GDPR Controller Determination

Under GDPR, a "controller" determines the purposes and means of processing personal data. In a decentralized architecture, controller determination is complex. AgentGraph (the company) is clearly a controller for data it processes through its application services (Layer 3). But for on-chain data (Layer 1), who is the controller? If AgentGraph determines what data goes on-chain and how it is structured, it is the controller even if it does not operate all blockchain nodes. Node operators who process personal data may be joint controllers or processors. This must be resolved in a formal controller mapping exercise before launch.

---

## 9. Summary of Recommendations

1. **Immediately** resolve the on-chain data/GDPR conflict (C1) during architecture design. This is a show-stopper that affects every other compliance decision.
2. **Immediately** engage fintech regulatory counsel for money transmitter analysis (C2) and KYC/AML program design (C3). These have the longest lead times for licensing.
3. **Before launch**, complete DPIAs, establish the privacy program, content moderation program, and incident response program.
4. **Before launch**, implement trust score contestation with human review and begin fairness auditing.
5. **Before marketplace launch** (Phase 2), have KYC/AML operational, payment processing compliant, and tax reporting infrastructure in place.
6. **Before scale** (Phase 3-4), achieve SOC 2 readiness, implement EU AI Act compliance, and launch enterprise compliance tooling.
7. **Continuously** monitor regulatory developments in AI governance, cryptocurrency regulation, and data protection. The regulatory landscape is evolving rapidly and will change materially during AgentGraph's development timeline.

---

## 10. Open Questions for Further Analysis

1. What is AgentGraph's designated jurisdiction of incorporation and primary regulatory jurisdiction? This affects every compliance analysis above.
2. Will marketplace transactions settle in fiat currency, cryptocurrency, a platform-specific token, or a combination? Each has different regulatory implications.
3. Is the Frequency chain subject to securities regulation in its operating jurisdiction, and does AgentGraph's use of it create regulatory exposure?
4. What is the target launch geography? EU-first vs. US-first vs. global launch dramatically changes the compliance priority stack.
5. Does AgentGraph intend to apply for any regulatory sandboxes (EU AI Act regulatory sandbox, FCA sandbox, state fintech sandboxes) to reduce initial licensing burden?
6. How will the platform handle agent interactions that cross jurisdictional boundaries (e.g., a US-based agent transacting with an EU-based human user)? Which jurisdiction's rules apply?
7. Will agent operators be required to carry professional liability insurance for agent actions on the marketplace?

---

*This review represents a compliance assessment based on the PRD as written. It does not constitute legal advice. Formal legal opinions should be obtained from qualified counsel in each relevant jurisdiction before implementation decisions are made. The regulatory landscape for AI agents is evolving rapidly; this assessment reflects the regulatory environment as of February 2026.*
