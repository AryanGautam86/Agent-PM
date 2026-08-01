import type { ReactNode } from 'react'

interface CardProps {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  accent?: 'default' | 'good' | 'warning' | 'attention'
  children: ReactNode
}

export function Card({
  title,
  subtitle,
  actions,
  accent = 'default',
  children,
}: CardProps) {
  return (
    <section className={`card card-accent-${accent}`}>
      {(title || actions) && (
        <header className="card-header">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="card-subtitle muted">{subtitle}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  )
}
