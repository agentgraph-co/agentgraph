interface AvatarProps {
  name: string
  url?: string | null
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizes = {
  sm: 'w-6 h-6 text-[10px]',
  md: 'w-10 h-10 text-sm',
  lg: 'w-16 h-16 text-xl',
}

export default function Avatar({ name, url, size = 'md', className = '' }: AvatarProps) {
  const sizeClass = sizes[size]
  const initials = name.charAt(0).toUpperCase()

  if (url) {
    return (
      <img
        src={url}
        alt={name}
        loading="lazy"
        className={`${sizeClass} rounded-full object-cover shrink-0 ${className}`}
      />
    )
  }

  return (
    <div
      className={`${sizeClass} rounded-full bg-surface-hover flex items-center justify-center font-bold text-text-muted shrink-0 ${className}`}
    >
      {initials}
    </div>
  )
}
