import { Link } from 'react-router-dom'

interface EmptyStateProps {
  icon: string
  title: string
  description: string
  action?: { label: string; to: string }
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <span className="text-5xl mb-4" role="img" aria-hidden="true">{icon}</span>
      <h2 className="text-lg font-semibold mb-2">{title}</h2>
      <p className="text-sm text-text-muted max-w-md mb-4">{description}</p>
      {action && (
        <Link
          to={action.to}
          className="text-sm font-medium text-primary-light hover:underline"
        >
          {action.label} &rarr;
        </Link>
      )}
    </div>
  )
}
