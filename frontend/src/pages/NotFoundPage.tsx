import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="center-screen">
      <div className="state-block">
        <p className="state-title">That page does not exist.</p>
        <Link className="link" to="/">
          Back to the dashboard
        </Link>
      </div>
    </div>
  )
}
