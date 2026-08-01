# Deployment

Three services: Supabase (database + auth), Render (backend), Vercel
(frontend). Set them up in that order — the other two need Supabase values.

## 1. Supabase

1. Create a project at [supabase.com](https://supabase.com). Note the region;
   put Render in the same one to keep latency down.
2. **Project Settings → API** — collect:
   - `Project URL` → `SUPABASE_URL` / `VITE_SUPABASE_URL`
   - `anon public` key → `VITE_SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY` (backend only — never
     ship this to the frontend)
3. **Project Settings → Database** — copy the **connection pooler** URI
   (transaction mode, port 6543). Convert it for asyncpg:

   ```
   postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
   ```

   Append `?prepared_statement_cache_size=0` — the transaction pooler does not
   support prepared statements and asyncpg uses them by default.

   Use the **direct** connection (port 5432) for `ALEMBIC_DATABASE_URL`;
   migrations need session-level features the transaction pooler lacks.

### Google OAuth

1. In Google Cloud Console create an **OAuth 2.0 Client ID** (Web application).
2. Authorised redirect URI: `https://<ref>.supabase.co/auth/v1/callback`
3. In Supabase → **Authentication → Providers → Google**, paste the client ID
   and secret, enable.
4. In Supabase → **Authentication → URL Configuration**, set the Site URL to
   your Vercel domain and add `http://localhost:5173` plus your Vercel preview
   domains to *Redirect URLs*.

### Email sign-in (code and link)

**Configure SMTP first.** On the free tier with Supabase's default sender,
email templates *cannot be edited* — the API rejects the change outright:

> *Email template modification is not available for free tier projects using
> the default email provider.*

That means no `{{ .Token }}`, so emails carry only a link and the code entry
screen has nothing to verify. Any custom SMTP unlocks template editing and
removes the few-per-hour, project-wide rate limit.

Under **Project Settings → Auth → SMTP** (or the Management API):

| Field | Gmail example |
| --- | --- |
| Host | `smtp.gmail.com` |
| Port | `465` — send it as a **string** via the Management API |
| Username | your full Gmail address |
| Password | a Google **App Password**, never the account password |
| Sender name | `Agent-PM` |

A Google App Password needs 2-Step Verification enabled, is generated at
[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
and is revocable on its own. Gmail rewrites `From` to the sending account, so
use a domain sender (Workspace SMTP relay, Resend, SES) for client-facing mail.

Then **Authentication → Email Templates**. Edit **both**:

- **Confirm signup** — used the first time an address signs in
- **Magic Link** — used every time after that

Including both `{{ .Token }}` and `{{ .ConfirmationURL }}` lets one email serve
the code and the link, so either path works.

### Redirect URLs

**Authentication → URL Configuration**: set Site URL to the app origin and add
the callback to the allow-list. Sign-in links redirect to the **Site URL**,
which is usually the protected root rather than `/auth/callback` — the app
handles a credential arriving on any route, but the origin must be allow-listed
or the link silently redirects somewhere that is not running.

### Schema

Run migrations from your machine against the direct connection:

```bash
cd backend
ALEMBIC_DATABASE_URL="postgresql+asyncpg://postgres:<pw>@db.<ref>.supabase.co:5432/postgres" \
  alembic upgrade head
```

## 2. Render (backend)

`render.yaml` at the repository root is a Render blueprint. Point Render at the
repo and it will pick it up, or create the service manually:

- **Environment:** Python 3
- **Root directory:** `backend`
- **Build command:** `pip install --upgrade pip && pip install -e .`
- **Start command:** `uvicorn agent_pm.main:app --host 0.0.0.0 --port $PORT`
- **Health check path:** `/api/v1/health/live`

Environment variables:

| Key | Value |
| --- | --- |
| `ENVIRONMENT` | `prod` |
| `DATABASE_URL` | pooler URI, asyncpg scheme, `?prepared_statement_cache_size=0` |
| `SUPABASE_URL` | project URL |
| `SUPABASE_ANON_KEY` | anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | service role key |
| `CORS_ORIGINS` | `["https://your-app.vercel.app"]` |
| `ANTHROPIC_API_KEY` | Anthropic key |
| `SCHEDULER_ENABLED` | `true` |
| `JIRA_*`, `GITHUB_*`, `TEAMS_*` | per `backend/.env.example`; omit to run on fixtures |

**Scheduler and instance count.** The scheduler runs in-process. Running more
than one Render instance would post each standup once per instance. Either keep
the web service at one instance, or set `SCHEDULER_ENABLED=false` on the web
service and run the scheduler as a separate Render background worker with the
same environment (`python -m agent_pm.scheduler.runner`). The blueprint takes
the second approach.

Render's free tier spins down when idle, which will drop scheduled posts — the
pilot needs at least the Starter plan.

## 3. Vercel (frontend)

- **Root directory:** `frontend`
- **Framework preset:** Vite
- **Build command:** `npm run build`
- **Output directory:** `dist`

Environment variables (all `VITE_`-prefixed vars are public by design — put
nothing secret here):

| Key | Value |
| --- | --- |
| `VITE_SUPABASE_URL` | project URL |
| `VITE_SUPABASE_ANON_KEY` | anon key |
| `VITE_API_BASE_URL` | `https://<your-render-service>.onrender.com` |

`frontend/vercel.json` rewrites all paths to `index.html` so client-side routes
survive a hard refresh.

After the first Vercel deploy, go back and add the Vercel domain to
`CORS_ORIGINS` on Render and to Supabase's redirect URL allowlist.

## 4. Never in production

`DEV_AUTH_BYPASS_EMAIL` disables authentication entirely. It is honoured only
when `ENVIRONMENT=local`, and the application raises on start-up if it is set
with any other environment — so a bad deploy fails its health check instead of
serving every request as one user. Do not add it to Render.

## 5. Post-deploy checklist

- [ ] `GET https://<render>/api/v1/health/ready` returns `"database": "ok"`
- [ ] Google sign-in redirects back to the app and lands on the dashboard
- [ ] Email OTP delivers a 6-digit code that verifies
- [ ] An authenticated `GET /api/v1/engagements` returns `[]` rather than 401
- [ ] Seed one engagement, then `POST /engagements/{id}/standups/morning`
- [ ] Scheduler worker logs show the morning and EOD jobs registered
- [ ] `CORS_ORIGINS` contains the production domain and no wildcard
