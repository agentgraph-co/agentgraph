/**
 * GradeCard — the giant letter grade display for the /check page.
 * Consumer-first: impossible-to-miss letter grade with color coding.
 */

import { getGradeInfo, type LetterGrade } from '../trust/gradeSystem'

interface GradeCardProps {
  grade: LetterGrade
  score: number // 0-100
  repoName: string
}

export default function GradeCard({ grade, score, repoName }: GradeCardProps) {
  const info = getGradeInfo(score)

  return (
    <div className="flex flex-col items-center text-center py-6">
      {/* Giant letter grade */}
      <div
        className={`w-28 h-28 sm:w-36 sm:h-36 rounded-2xl flex items-center justify-center font-black text-6xl sm:text-7xl ${info.bgClass} border-2`}
        style={{ color: info.color, borderColor: `${info.color}30` }}
      >
        {grade}
      </div>

      {/* Numeric score */}
      <div className="flex items-baseline gap-1.5 mt-4">
        <span className="text-3xl font-bold text-text-primary">{score}</span>
        <span className="text-sm text-text-muted">/ 100</span>
      </div>

      {/* Grade label */}
      <p className="text-sm font-semibold mt-1" style={{ color: info.color }}>
        {info.label}
      </p>

      {/* Repo name */}
      <p className="text-xs text-text-muted mt-2 font-mono">{repoName}</p>
    </div>
  )
}
