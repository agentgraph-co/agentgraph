/**
 * SafetySummary — plain English verdict for consumers.
 * Shows clear Safe / Caution / Not Recommended verdict with explanation.
 */

import type { LetterGrade } from '../trust/gradeSystem'

interface SafetySummaryProps {
  grade: LetterGrade
  totalFindings: number
  criticalFindings: number
  providerCount: number
}

interface VerdictInfo {
  verdict: string
  summary: string
  icon: string
  colorClass: string
  bgClass: string
  borderClass: string
}

function getVerdict(grade: LetterGrade, criticalFindings: number): VerdictInfo {
  if (grade === 'A+' || grade === 'A') {
    return {
      verdict: 'Safe to Use',
      summary: criticalFindings === 0
        ? 'No critical security issues found. This agent follows security best practices.'
        : 'Minor issues found but overall security posture is strong.',
      icon: '\u2714',
      colorClass: 'text-teal-400',
      bgClass: 'bg-teal-500/10',
      borderClass: 'border-teal-500/20',
    }
  }
  if (grade === 'B') {
    return {
      verdict: 'Generally Safe',
      summary: 'Some minor issues detected. Review the findings before use in production.',
      icon: '\u2714',
      colorClass: 'text-green-500',
      bgClass: 'bg-green-500/10',
      borderClass: 'border-green-500/20',
    }
  }
  if (grade === 'C') {
    return {
      verdict: 'Use with Caution',
      summary: 'Moderate security concerns found. Review findings carefully before use.',
      icon: '\u26A0',
      colorClass: 'text-amber-500',
      bgClass: 'bg-amber-500/10',
      borderClass: 'border-amber-500/20',
    }
  }
  if (grade === 'D') {
    return {
      verdict: 'Use with Caution',
      summary: 'Significant security issues detected. Not recommended for sensitive use cases.',
      icon: '\u26A0',
      colorClass: 'text-orange-500',
      bgClass: 'bg-orange-500/10',
      borderClass: 'border-orange-500/20',
    }
  }
  // F
  return {
    verdict: 'Not Recommended',
    summary: 'Critical security issues found. This agent has serious vulnerabilities that need to be addressed.',
    icon: '\u2718',
    colorClass: 'text-red-500',
    bgClass: 'bg-red-500/10',
    borderClass: 'border-red-500/20',
  }
}

export default function SafetySummary({ grade, totalFindings, criticalFindings, providerCount }: SafetySummaryProps) {
  const v = getVerdict(grade, criticalFindings)

  return (
    <div className={`rounded-lg border p-4 sm:p-5 ${v.bgClass} ${v.borderClass}`}>
      {/* Verdict */}
      <div className="flex items-center gap-3 mb-3">
        <span className={`text-2xl ${v.colorClass}`} aria-hidden="true">{v.icon}</span>
        <h2 className={`text-lg sm:text-xl font-bold ${v.colorClass}`}>{v.verdict}</h2>
      </div>

      {/* Summary text */}
      <p className="text-sm text-text-primary leading-relaxed">{v.summary}</p>

      {/* Stats bar */}
      <div className="flex flex-wrap gap-4 mt-4 text-xs text-text-muted">
        <span>{totalFindings} finding{totalFindings !== 1 ? 's' : ''} total</span>
        {criticalFindings > 0 && (
          <span className="text-red-400">{criticalFindings} critical</span>
        )}
        {providerCount > 0 && (
          <span>Verified by {providerCount} provider{providerCount !== 1 ? 's' : ''}</span>
        )}
      </div>
    </div>
  )
}
