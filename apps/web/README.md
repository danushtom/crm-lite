# Dracara Growth OS — Web

Next.js 15 (App Router) frontend. It never talks to Postgres directly outside of authentication — every read and write of business data goes through the FastAPI backend (`apps/api`), which is itself subject to row-level security. The frontend's own job is presentation, client-side state, and calling that API correctly.

## 1. Layout

```text
app/
├── layout.tsx           # root layout: fonts, providers, theme
├── page.tsx             # redirects to /dashboard
├── login/                # unauthenticated route, outside the (app) group
└── (app)/                # every authenticated page, wrapped in the app shell
    ├── dashboard/
    ├── contacts/          # list + contacts/[id] detail
    ├── leads/              # list + leads/[id] detail, with its own sub-routes
    ├── opportunities/      # Kanban board + opportunities/[id] detail
    ├── companies/
    ├── follow-ups/
    ├── calendar/
    ├── reports/
    ├── settings/
    ├── agents/             # team/user management: invite, roles, permissions
    └── voice-agents/       # AI voice-calling agents: create, phone numbers, call log
components/
├── layout/               # AppShell, top bar, notification bell
├── shared/               # EntityDrawer and the form-field primitives every drawer uses
├── <resource>/           # one folder per resource, e.g. contacts/, leads/, voice-agents/
lib/
├── api.ts                # apiFetch/apiList/apiPage/apiListAll — the only way to call the backend
├── use-api-mutation.ts   # useMutation wrapper with a default error toast
├── forms.ts              # compactPayload and other form-to-request-body helpers
└── supabase/             # browser and server Supabase clients (auth only)
```

`packages/types` and `packages/ui` are shared workspace packages, not part of this app: `@dracara/types` mirrors the API's Pydantic response shapes, and `@dracara/ui` wraps the shadcn/ui primitives used everywhere (`Button`, `Card`, `Input`, and so on).

## 2. Talking to the API

Every request goes through `lib/api.ts`, never through a raw `fetch`:

| Helper | Use for |
| --- | --- |
| `apiFetch<T>(path, init)` | A single resource, or any non-list response. Attaches the current Supabase access token; throws `ApiError` on a non-2xx response. |
| `apiFetchOptional<T>(path)` | A one-to-one lookup that may legitimately not exist — returns `null` on 404, still throws on everything else. |
| `apiPage<T>(path)` | One page of a paginated collection, keeping `{items, page}`. |
| `apiList<T>(path)` | One page of a collection, discarding the pagination metadata. |
| `apiListAll<T>(path)` | Every page of a collection, for views that need the full set client-side (for example, a Kanban board). Capped at 20 pages. |

`apiFetch` automatically switches to a plain (non-JSON) `Content-Type` when the request body is `FormData`, so file uploads (proposal documents, voice-agent knowledge-base documents) go through the same helper as everything else.

`ApiError` carries the backend's RFC 9457 Problem Details fields (`status`, `code`, `detail`, `fieldErrors`) — `describeError()` in `lib/use-api-mutation.ts` turns one into a one-line message for a toast.

## 3. The drawer pattern

Every create/edit form in this app is a slide-in panel built on `EntityDrawer` (`components/shared/entity-drawer.tsx`), not a separate page or a modal dialog. A typical resource drawer (see `components/contacts/contact-drawer.tsx` or `components/voice-agents/voice-agent-drawer.tsx` for reference implementations):

1. Takes an optional `<Resource>` prop — its presence distinguishes edit mode from create mode.
2. Holds its form state as a plain object, seeded from the prop when editing.
3. Fetches whatever reference data it needs (a company list for a contact, a phone-number list for a voice agent) via `useQuery`, gated with `enabled: open` so it only fires while the drawer is actually open.
4. Submits via `useApiMutation`, and invalidates the relevant list `useQuery` keys in `onSuccess` so the underlying page re-fetches automatically.

`Field`, `TextField`, `TextareaField`, and `SelectField` in `entity-drawer.tsx` are the shared form primitives — reach for these before writing a new input wrapper.

## 4. State management

TanStack Query v5 owns all server state. There is no separate global store for API data. Conventions worth keeping:

- Query keys are arrays that mirror the resource and any active filter, e.g. `["voice-agents", "calls"]`.
- A mutation's `onSuccess` invalidates every query key its write could affect — including a related resource's key, not only the one it directly wrote to (for example, changing a voice agent's phone number invalidates both `["voice-agents"]` and the phone-number list).
- Optimistic updates are used sparingly, mainly for Kanban drag-and-drop (`components/pipeline/kanban-board.tsx`).

## 5. Adding a page or resource

1. Add the API response shape to `packages/types/src/index.ts`, matching the backend's Pydantic model field-for-field.
2. Build a `<resource>-drawer.tsx` in `components/<resource>/` following Section 3.
3. Build the list/detail page under `app/(app)/<resource>/`, fetching through `lib/api.ts`'s helpers.
4. Add a navigation entry in `components/layout/app-shell.tsx` if the page needs one in the sidebar.

## 6. Running and testing

```bash
pnpm --filter web dev     # http://localhost:3000
pnpm --filter web build   # production build; also runs type-checking and lint
pnpm --filter web lint
pnpm --filter web test    # Vitest is configured; no test files exist yet, so this passes trivially
```

See `../../SETUP.md` for environment variables and the rest of the stack.
