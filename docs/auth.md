# Auth

Self-hosted JWT in HTTP-only cookies. No public signup. Roles: `admin`, `recruiter`.

## How a request gets authenticated

1. Browser submits credentials to `POST /api/auth/login`.
2. API verifies the password against the argon2 hash in `users.password_hash`.
3. On success, API issues a signed JWT (HS256, 24h TTL) and sets it as an HTTP-only, `SameSite=Lax`, `Secure` (in prod) cookie named `hiremesh_session`.
4. Subsequent requests include the cookie automatically. The `current_user` dependency in `app/core/deps.py` decodes the JWT, looks up the user, and injects them into the route handler.

The cookie is the **only** auth surface. There are no Authorization headers, no API tokens. Tokens can't leak through `localStorage` because they never live there.

## Roles

- **`admin`** — can create users (`POST /users`) and (later) edit the system-wide stage template.
- **`recruiter`** — everything else. The default role for new users.

Endpoints that require admin use `Depends(require_admin)`, which is a thin gate on top of `current_user`. A recruiter calling an admin-only endpoint gets a `403`, not a `401`.

## First admin (post-deploy CLI)

Public signup is disabled. The first admin in a fresh deployment is created via the CLI at `app/cli.py`:

```bash
make admin-create EMAIL=you@example.com NAME="Your Name"
# Password: ******** (interactive prompt, echo off, min 12 chars)
# Confirm:  ********
```

That target just shells `docker compose exec api python -m app.cli admin create ...`. The same CLI lets you reset a forgotten password (`make admin-set-password EMAIL=...`) or list current admins (`make admin-list`). See [`ops.md`](./ops.md#admin-user-management) for full ops details.

There is **no env-based bootstrap admin** — `BOOTSTRAP_ADMIN_*` env vars no longer exist. Storing a password in plaintext in `.env`, only honoured on first-empty-table boot, was a prod hazard: the env file gets backed up, copied between hosts, sometimes committed by accident. Using the CLI keeps the password ephemeral (lives in your terminal session, then in argon2-hashed form in the DB).

## Adding more users

After first boot, only an admin can create new users. From an admin session:

```http
POST /api/users
Content-Type: application/json
Cookie: hiremesh_session=…

{
  "email": "new@example.com",
  "name": "New Recruiter",
  "password": "temp-password-for-them",
  "role": "recruiter"
}
```

The new user is created with `must_change_password=true`. They sign in with the temp password and call `POST /api/auth/me/password` to set their own.

## Endpoints

| Method | Path | Auth | What it does |
|---|---|---|---|
| `POST` | `/api/auth/login` | none | Verify credentials, set session cookie. |
| `POST` | `/api/auth/logout` | none | Clear the session cookie. |
| `GET`  | `/api/auth/me` | cookie | Return the logged-in user. |
| `POST` | `/api/auth/me/password` | cookie | Change own password (requires current). |
| `POST` | `/api/users` | admin | Create a user. |

## Securing the cookie in production

Set in `infra/.env`:

```
COOKIE_SECURE=true
```

This adds the `Secure` flag, so browsers only send the cookie over HTTPS. Caddy terminates TLS in front of the API in production deployments.

## Why no refresh tokens?

For a single-tenant agency tool with a 24h session, refresh tokens add complexity without a strong reason. If a session expires mid-flow, the user signs in again. We can revisit this if/when usage patterns demand it.

## What's not in v1

- Password reset / "forgot password" flows
- Email-based invites (admin-supplied temp passwords for now)
- Forced password-change UI guard (the flag exists; the UI gate ships in M1+)
- Refresh tokens, MFA, SSO

These are deferred deliberately — they each need their own design pass and aren't worth bundling into M0.

## Code map

| Concern | File |
|---|---|
| User model | `app/models/user.py` |
| Password hashing & JWT | `app/core/security.py` |
| Auth dependency | `app/core/deps.py` |
| Login/logout/me/change-password handlers | `app/api/auth.py` |
| Admin user creation (in-app) | `app/api/users.py` |
| User-creation service helper | `app/services/users.py` |
| Post-deploy admin CLI | `app/cli.py` |
| Cookie/JWT settings | `app/core/config.py` |
| Auth flow tests | `backend/tests/test_auth.py` |
| CLI tests | `backend/tests/test_cli.py` |
