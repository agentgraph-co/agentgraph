/**
 * Scan-category registry — the single source of truth mapping every backend
 * finding `category` key to its human display (label / icon / description / sub-score
 * family). New scanner categories MUST be added here so they render with a proper
 * label instead of a raw key. Keys mirror src/scanner/scan.py finding categories.
 */

export type ScoreFamily =
  | 'secret_hygiene'
  | 'code_safety'
  | 'data_handling'
  | 'filesystem_access'
  | 'dependency_health'

export interface CategoryInfo {
  key: string
  label: string
  icon: string
  description: string
  family: ScoreFamily
}

// All 12 backend finding categories (src/scanner/scan.py). Ordered roughly by
// how agent-native / novel the threat is (the newest, MCP-specific ones first
// after secrets, since they are the differentiated detections).
export const SCAN_CATEGORIES: Record<string, CategoryInfo> = {
  secret: {
    key: 'secret',
    label: 'Hardcoded Secret',
    icon: '🔑', // 🔑
    description: 'Credentials, API keys, or tokens committed directly in source.',
    family: 'secret_hygiene',
  },
  prompt_injection: {
    key: 'prompt_injection',
    label: 'Prompt Injection',
    icon: '💉', // 💉
    description:
      'Instruction-override / hidden-directive text in a tool description or manifest — poisons the agent that reads the tool.',
    family: 'code_safety',
  },
  dynamic_remote_load: {
    key: 'dynamic_remote_load',
    label: 'Rug-Pull / Remote Load',
    icon: '🎣', // 🎣
    description:
      'Fetches code, config, or tool definitions from a mutable remote source that can be swapped after you integrate it.',
    family: 'code_safety',
  },
  toxic_flow: {
    key: 'toxic_flow',
    label: 'Lethal Trifecta',
    icon: '☠️', // ☠️
    description:
      'Combines private-data access, untrusted-input ingestion, and outbound send — the prompt-injection → exfiltration chain.',
    family: 'data_handling',
  },
  hidden_unicode: {
    key: 'hidden_unicode',
    label: 'Hidden Unicode',
    icon: '👻', // 👻
    description:
      'Invisible, bidi, or tag Unicode that can smuggle instructions a human reviewer never sees.',
    family: 'code_safety',
  },
  insecure_deserialization: {
    key: 'insecure_deserialization',
    label: 'Insecure Deserialization',
    icon: '🧬', // 🧬
    description:
      'Deserializes untrusted data (pickle / marshal / yaml.load) that can execute arbitrary code.',
    family: 'code_safety',
  },
  install_hook: {
    key: 'install_hook',
    label: 'Install Hook',
    icon: '⛓️', // ⛓️
    description:
      'npm pre/post-install lifecycle script that auto-runs on install — a top supply-chain vector.',
    family: 'dependency_health',
  },
  unsafe_exec: {
    key: 'unsafe_exec',
    label: 'Unsafe Execution',
    icon: '⚠️', // ⚠️
    description: 'Dynamic or shell code execution (subprocess, eval/exec, shell=True).',
    family: 'code_safety',
  },
  exfiltration: {
    key: 'exfiltration',
    label: 'Data Exfiltration',
    icon: '📡', // 📡
    description: 'Sensitive data sent to an outbound or known-exfil endpoint.',
    family: 'data_handling',
  },
  fs_access: {
    key: 'fs_access',
    label: 'Filesystem Access',
    icon: '📁', // 📁
    description: 'Unsandboxed file read/write, path traversal, or recursive delete.',
    family: 'filesystem_access',
  },
  obfuscation: {
    key: 'obfuscation',
    label: 'Code Obfuscation',
    icon: '🕵️', // 🕵️
    description: 'Obfuscated or encoded code that hides what it actually does.',
    family: 'code_safety',
  },
  dependency: {
    key: 'dependency',
    label: 'Vulnerable Dependency',
    icon: '📦', // 📦
    description: 'Depends on a package version with a known CVE.',
    family: 'dependency_health',
  },
}

/** Look up a category, with a graceful fallback for any unknown/new key. */
export function getCategoryInfo(key: string): CategoryInfo {
  return (
    SCAN_CATEGORIES[key] ?? {
      key,
      label: key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase()),
      icon: '🔍', // 🔍
      description: 'Security finding.',
      family: 'code_safety',
    }
  )
}

// The five sub-score axes the scanner reports (category_scores), with display labels.
export const SUBSCORE_LABELS: Record<ScoreFamily, string> = {
  secret_hygiene: 'Secret Hygiene',
  code_safety: 'Code Safety',
  data_handling: 'Data Handling',
  filesystem_access: 'Filesystem Access',
  dependency_health: 'Dependency Health',
}

export const SUBSCORE_ORDER: ScoreFamily[] = [
  'secret_hygiene',
  'code_safety',
  'data_handling',
  'filesystem_access',
  'dependency_health',
]
