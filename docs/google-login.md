# Google Login

EC Pulse API uses Supabase Auth for Google OAuth.

## Required environment

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
APP_BASE_URL=https://ec-pulse-api.vercel.app
```

The publishable key is safe for browser/application use. Never put a Supabase secret/service-role key in the client.

## Supabase setup

Enable **Google** under Authentication → Providers in the Supabase project.

Configure the Google OAuth client in Google Cloud and register the Supabase callback URL shown by the Supabase Google provider settings.

Add the EC Pulse callback URL to the Supabase redirect allow list:

```text
https://ec-pulse-api.vercel.app/auth/callback
```

For local development:

```text
http://localhost:8000/auth/callback
```

## Endpoints

- `GET /auth/google` — starts Google login with PKCE.
- `GET /auth/callback` — exchanges the OAuth code and establishes an HTTP-only session cookie.
- `GET /auth/me` — returns the authenticated Supabase user.
- `POST /auth/logout` — clears the local session cookies.

The OAuth verifier and access/refresh tokens are stored in HTTP-only cookies. The API-key authentication used by the paid API remains separate; Google login does not replace API keys or their request-signature mechanism.
