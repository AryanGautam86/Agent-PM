# Agent-PM frontend

React 19 + TypeScript + Vite SPA for the Delivery Steward. Deploys to Vercel.

## Running locally

```bash
cp .env.example .env.local   # fill in Supabase URL + anon key
npm install
npm run dev                  # http://localhost:5173
```

With `VITE_API_BASE_URL` empty, Vite proxies `/api` to `http://localhost:8000`,
so the browser sees a single origin and CORS is not involved in development.

| Command             | Purpose                       |
| ------------------- | ----------------------------- |
| `npm run dev`       | Dev server with HMR           |
| `npm run build`     | Typecheck, then production build |
| `npm run typecheck` | Types only                    |
| `npm run lint`      | ESLint                        |
| `npm test`          | Vitest                        |

## Structure

```
src/
├── app/          Router and providers — composition only
├── components/
│   ├── layout/   AppShell (sidebar, engagement picker)
│   └── ui/       Button, Card, Badge, Spinner, states, markdown
├── features/     One folder per domain area
│   ├── auth/     AuthProvider, login (Google + OTP), route guard
│   ├── dashboard/
│   ├── standups/
│   ├── raid/
│   ├── action_items/
│   ├── approvals/
│   └── reports/
├── hooks/        Cross-feature hooks (engagement selection)
├── lib/          Supabase client, API client, query keys, formatting
├── pages/        Route-level pages with no feature of their own
├── store/        Zustand — selected engagement only
├── styles/       Design tokens and component CSS
└── types/        API types mirroring the backend schemas
```

Conventions:

- **A feature owns its data access.** Each `features/*/api.ts` holds that
  area's TanStack Query hooks. Components never call `fetch` directly.
- **`lib/api-client.ts` is the only place a request is made.** It attaches the
  Supabase access token and normalises errors into `ApiRequestError`.
- **The SPA never queries Supabase tables.** Supabase is used for auth only;
  all data goes through the API so grounding and approval rules cannot be
  bypassed by the client.
- **Server state lives in TanStack Query, client state in Zustand.** The store
  holds one thing — which engagement is selected — and nothing that the server
  already knows.

## Authentication

Two methods, both through Supabase Auth:

1. **Google** — `signInWithOAuth`, redirecting to `/auth/callback`.
2. **Email OTP** — `signInWithOtp` sends a 6-digit code, `verifyOtp` checks it.

The access token goes to the backend as a bearer token; the backend verifies it
against Supabase's JWKS and provisions a profile row on first request. The
first person to sign in becomes an admin so there is somebody who can assign
roles.

For OTP to deliver a code rather than only a magic link, the Supabase **Magic
Link** email template must include `{{ .Token }}`. See `docs/DEPLOYMENT.md`.
