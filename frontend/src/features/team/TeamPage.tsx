/**
 * Pod membership and roles — the other half of authentication.
 *
 * Two different roles are on show here and they are deliberately separate:
 *
 * - **Pod role** is what someone does on this engagement (tech lead, QA…).
 *   It is descriptive; the agent uses it for context.
 * - **App role** is what someone is allowed to do, and only it grants the
 *   right to decide approvals. It is never read from the token — an admin
 *   sets it here — so a claim in a JWT can never grant approval rights.
 */

import { useState, type FormEvent } from 'react'

import { Badge, StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState, ErrorState } from '@/components/ui/States'
import { useAuth } from '@/features/auth/useAuth'
import {
  useAddMember,
  useMembers,
  useRemoveMember,
  useSetAppRole,
} from '@/features/team/api'
import { useSelectedEngagement } from '@/hooks/useEngagements'
import { relativeTime, titleCase } from '@/lib/format'
import type { AppRole, PodRole } from '@/types/api'

const POD_ROLES: PodRole[] = [
  'product_owner',
  'delivery_lead',
  'tech_lead',
  'engineer',
  'qa',
  'designer',
]

const APP_ROLES: AppRole[] = ['admin', 'delivery_lead', 'product_owner', 'engineer']
const CAN_APPROVE: AppRole[] = ['admin', 'delivery_lead', 'product_owner']

export function TeamPage() {
  const { user } = useAuth()
  const { engagement, engagementId } = useSelectedEngagement()

  const members = useMembers(engagementId)
  const addMember = useAddMember(engagementId)
  const removeMember = useRemoveMember(engagementId)
  const setAppRole = useSetAppRole(engagementId)

  const [email, setEmail] = useState('')
  const [podRole, setPodRole] = useState<PodRole>('engineer')

  const isAdmin = user?.role === 'admin'

  function handleAdd(event: FormEvent) {
    event.preventDefault()
    if (!email.trim()) return
    addMember.mutate(
      { email: email.trim(), pod_role: podRole },
      { onSuccess: () => setEmail('') },
    )
  }

  if (!engagement) {
    return <EmptyState title="No engagement selected" />
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Team</h1>
          <p className="muted">
            Membership decides who can see this engagement. App role decides who
            can approve the agent&rsquo;s proposals.
          </p>
        </div>
      </header>

      <Card
        title="You"
        subtitle={user?.email}
        actions={
          user?.role && CAN_APPROVE.includes(user.role) ? (
            <Badge tone="success">can approve</Badge>
          ) : (
            <Badge tone="muted">cannot approve</Badge>
          )
        }
      >
        <dl className="detail-grid">
          <dt>App role</dt>
          <dd>{titleCase(user?.role ?? 'unknown')}</dd>
          <dt>Signed in with</dt>
          <dd>
            {user?.auth_provider === 'dev-bypass' ? (
              <Badge tone="danger">local dev bypass — no real sign-in</Badge>
            ) : (
              titleCase(user?.auth_provider ?? 'unknown')
            )}
          </dd>
        </dl>
        {user?.auth_provider === 'dev-bypass' && (
          <p className="alert alert-warning">
            Authentication is disabled because <code>DEV_AUTH_BYPASS_EMAIL</code>{' '}
            is set on the backend. This only works when{' '}
            <code>ENVIRONMENT=local</code>; the server refuses to start with it
            set anywhere else. Remove it once Supabase is configured.
          </p>
        )}
      </Card>

      <Card title="Add someone to the pod">
        <form className="inline-form" onSubmit={handleAdd}>
          <input
            type="email"
            placeholder="teammate@company.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            disabled={addMember.isPending}
            required
          />
          <select
            value={podRole}
            onChange={(event) => setPodRole(event.target.value as PodRole)}
            disabled={addMember.isPending}
          >
            {POD_ROLES.map((role) => (
              <option key={role} value={role}>
                {titleCase(role)}
              </option>
            ))}
          </select>
          <Button type="submit" variant="primary" loading={addMember.isPending}>
            Add
          </Button>
        </form>
        {addMember.isError && <ErrorState error={addMember.error} />}
        <p className="muted">
          They must have signed in at least once, so that an account exists to
          add.
        </p>
      </Card>

      {(removeMember.isError || setAppRole.isError) && (
        <ErrorState error={removeMember.error ?? setAppRole.error} />
      )}

      {members.isLoading ? (
        <Spinner label="Loading the pod" />
      ) : members.error ? (
        <ErrorState error={members.error} onRetry={() => void members.refetch()} />
      ) : (
        <Card title={`Pod members (${members.data?.length ?? 0})`}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Pod role</th>
                  <th>App role</th>
                  <th>Last seen</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {members.data?.map((member) => (
                  <tr key={member.id}>
                    <td>
                      <strong>{member.user.full_name ?? member.user.email}</strong>
                      <br />
                      <span className="muted">{member.user.email}</span>
                    </td>
                    <td>
                      <StatusBadge value={member.pod_role} />
                    </td>
                    <td>
                      {isAdmin ? (
                        <select
                          value={member.user.role}
                          disabled={setAppRole.isPending}
                          onChange={(event) =>
                            setAppRole.mutate({
                              userId: member.user_id,
                              role: event.target.value as AppRole,
                            })
                          }
                        >
                          {APP_ROLES.map((role) => (
                            <option key={role} value={role}>
                              {titleCase(role)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        titleCase(member.user.role)
                      )}
                      {CAN_APPROVE.includes(member.user.role) && (
                        <Badge tone="success">approver</Badge>
                      )}
                    </td>
                    <td className="muted">
                      {member.user.last_seen_at
                        ? relativeTime(member.user.last_seen_at)
                        : 'never signed in'}
                    </td>
                    <td>
                      {member.user_id !== user?.id && (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={removeMember.isPending}
                          onClick={() => removeMember.mutate(member.user_id)}
                        >
                          Remove
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!isAdmin && (
            <p className="muted">
              Only an administrator can change app roles.
            </p>
          )}
        </Card>
      )}
    </div>
  )
}
