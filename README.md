# LinkedIn Profile API

A public HTTPS API that accepts a LinkedIn profile URL and returns the information on that page as structured JSON.

It talks to LinkedIn the same way linkedin.com does: **direct HTTP calls to Voyager** (`/voyager/api/...`). There is **no browser**, no Playwright, and no official partner API.

A cookie-free guest path (public JSON-LD) is used automatically when the Voyager session is missing or dead.

> This is a research / challenge build. It uses LinkedIn’s **undocumented internal API**. That violates LinkedIn’s User Agreement. Do not run it as a product, at scale, or against people who have not consented. Your account can be restricted.

## Features

- `GET` / `POST /v1/profile` — profile URL in, JSON out
- Voyager path: name, headline, location, about, experience, education, skills, certifications, languages, projects, volunteer, honors, profile and background images
- Guest fallback: name, headline, location, photo, current org, schools (whatever the public page embeds)
- Optional `API_KEY` so a public URL cannot drain your LinkedIn session
- Secrets stay in environment variables, never in the repo

## How it works

```
Client  →  FastAPI  →  Voyager (li_at + JSESSIONID)
                         ↓ 401 / 403 / 999 / unconfigured
                       Public /in/{slug} HTML → JSON-LD Person
```

### Voyager (primary)

LinkedIn’s own web app loads profiles from:

```
GET https://www.linkedin.com/voyager/api/identity/dash/profiles
  ?q=memberIdentity
  &memberIdentity={public_id}
  &decorationId=com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-96
```

Authentication is a normal member session:

- Cookie `li_at` — session
- Cookie `JSESSIONID` — source of the `csrf-token` header (quotes stripped; the `ajax:` prefix stays)
- `Accept: application/vnd.linkedin.normalized+json+2.1`
- `x-restli-protocol-version: 2.0.0`

Requests go through **`curl_cffi` with Chrome TLS impersonation**. LinkedIn fronts Voyager with PerimeterX; a default Python TLS fingerprint is a common HTTP 999. The User-Agent is **not** overridden so it stays consistent with the impersonated handshake.

Decoration IDs rotate (wrong suffix → HTTP 400). The client walks a short list (`FullProfileWithEntities-96` → `-93` → `-91` → `-86` → `WebTopCardCore-16`), then tries GraphQL `queryName=voyagerIdentityDashProfiles` with `(vanityName:{slug})`. The legacy `identity/profiles/{id}/profileView` endpoint is a last resort; it currently returns **HTTP 410**.

The body is REST.li **normalized JSON**: a `data` graph plus an `included[]` array. `*field` keys are URN pointers. The parser indexes `included` by `entityUrn` and maps `$type` suffixes:

| `$type` suffix | Section |
| --- | --- |
| `identity.profile.Profile` | Identity, about, images |
| `identity.profile.Position` | Experience |
| `identity.profile.Education` | Education |
| `identity.profile.Skill` | Skills |
| `identity.profile.Certification` | Certifications |
| `identity.profile.Language` | Languages |
| `identity.profile.Project` / `VolunteerExperience` / `Honor` | Extra sections |

Images are `vectorImage.rootUrl + artifacts[].fileIdentifyingUrlPathSegment`, largest width first. Each artifact has its own signed `t=` token — do not rewrite widths.

### Guest fallback

`GET https://www.linkedin.com/in/{slug}` (still no browser). The public page embeds schema.org JSON-LD (`Person` or `ProfilePage.mainEntity`). That payload is thinner and often missing on authwalled requests.

The JSON `source` field tells you which tier served the response: `"voyager"` or `"guest"`.

## Setup

Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Capture cookies (required for full profiles)

1. Sign in to [linkedin.com](https://www.linkedin.com) in Chrome.
2. Open DevTools → **Application** → **Cookies** → `https://www.linkedin.com`.
3. Copy **`li_at`** and **`JSESSIONID`** into `.env`:

```
LINKEDIN_LI_AT=AQED...
LINKEDIN_JSESSIONID="ajax:1234567890123456789"
```

Keep the quotes around `JSESSIONID` if Chrome shows them. The client strips them only for the `csrf-token` header.

Optional:

```
# Extra cookies (bcookie, lidc, li_rm, PerimeterX _px3, …) as a raw Cookie header
LINKEDIN_EXTRA_COOKIES=bcookie=...; lidc=...

# Protect the public API
API_KEY=choose-a-long-random-string
```

`li_at` typically lasts months. It dies on password change, checkpoint, or LinkedIn invalidating the session. There is **no email/password auto-login** — that flow hits CAPTCHA from datacenter IPs.

### Run locally

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

```bash
curl -s "http://127.0.0.1:8000/health"
curl -s "http://127.0.0.1:8000/v1/profile?url=https://www.linkedin.com/in/williamhgates/"
```

If `API_KEY` is set:

```bash
curl -s -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/v1/profile?url=https://www.linkedin.com/in/williamhgates/"
```

### Tests

```bash
pytest
```

Tests cover URL parsing, Voyager `$type` mapping, guest JSON-LD, and HTTP error mapping. They do **not** call LinkedIn.

## API

### `GET /health`

Liveness. If cookies are configured, probes `GET /voyager/api/me`.

```json
{
  "status": "ok",
  "voyager": { "configured": true, "session": "live" }
}
```

`session` is `live`, `dead`, `unknown`, or `unconfigured`.

### `GET /v1/profile?url=`

### `POST /v1/profile`

```json
{ "url": "https://www.linkedin.com/in/williamhgates/" }
```

Accepted URL shapes: `https` / `http`, `www` / bare / country subdomain, trailing slash, query strings, `/in/{slug}/overlay/...`, `/mwlite/in/{slug}`. Company, school, jobs, and feed URLs return **400**.

#### Response

```json
{
  "source": "voyager",
  "url": "https://www.linkedin.com/in/williamhgates/",
  "public_id": "williamhgates",
  "urn": "urn:li:fsd_profile:...",
  "first_name": "Bill",
  "last_name": "Gates",
  "full_name": "Bill Gates",
  "headline": "...",
  "about": "...",
  "location": { "name": "Seattle, Washington", "country": "US" },
  "industry": "...",
  "profile_picture": { "url": "https://media.licdn.com/..." },
  "background_image": { "url": "..." },
  "experience": [
    {
      "title": "",
      "company": "",
      "company_url": null,
      "location": null,
      "description": null,
      "start": "2015-01",
      "end": null,
      "is_current": true
    }
  ],
  "education": [
    { "school": "", "degree": null, "field": null, "start": null, "end": null }
  ],
  "skills": [{ "name": "" }],
  "certifications": [{ "name": "", "authority": null, "issued": null }],
  "languages": [{ "name": "", "proficiency": null }],
  "projects": [],
  "volunteer": [],
  "honors": []
}
```

Missing fields are `null` or `[]`. Dates are `YYYY-MM` when a month is present, otherwise `YYYY`.

#### Errors

| Status | Meaning |
| --- | --- |
| 400 | Not a member profile URL |
| 401 | Missing / wrong `X-API-Key` (only if `API_KEY` is set) |
| 404 | Profile does not exist |
| 429 | Local limiter or LinkedIn rate limit |
| 502 | LinkedIn blocked the request (HTTP 999 / authwall) on both tiers |
| 503 | Voyager session unavailable and guest fallback also failed |

An in-process limiter caps concurrent LinkedIn work and request rate so a public deploy cannot immediately burn the session.

## Deploy on Railway

Railway (2026) uses **Railpack**. This app lives in `app/main.py`, so it will **not** auto-start as `main:app`. The repo includes a `Procfile`:

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

If Railpack ignores the Procfile, set the service start command to that same line. Bind `0.0.0.0` and `$PORT` or you will get a 502 from the edge proxy.

### CLI

```bash
# macOS
brew install railway

railway login
railway init --name linkedin-profile-api
railway variable set LINKEDIN_LI_AT=...
railway variable set LINKEDIN_JSESSIONID=...
railway variable set API_KEY=...
railway up
railway domain
```

Or connect the GitHub repo in the Railway dashboard (autodeploy on push) and set the same variables under **Variables**. Generate a public domain under **Settings → Networking**. TLS is automatic on `*.up.railway.app`.

Never commit `.env`. Railway variables are the source of truth in production.

### Outbound IP warning

Railway egress is a **shared datacenter range**. LinkedIn often answers **HTTP 999** from those IPs. `curl_cffi` fixes TLS fingerprinting, not IP reputation. If Voyager is blocked, the guest path still runs; if both fail you get 502. A residential proxy in front of this service is the durable fix. Railway static outbound IPs (Pro) are still datacenter addresses.

## Project layout

```
app/
  main.py                 FastAPI routes
  config.py               Environment settings
  models.py               Response schema
  linkedin/
    client.py             curl_cffi Voyager session
    voyager.py            dash/profiles + decoration walk
    parsers.py            normalized JSON → Profile
    guest.py              public JSON-LD fallback
    urls.py               /in/{slug} extractor
    service.py            tiered resolver
    limiter.py            in-process rate limit
tests/
```

## Known limitations

- Voyager is unofficial. Decoration IDs and GraphQL `queryId` hashes rotate without notice.
- `li_at` expires. There is no password re-login (CAPTCHA / checkpoint from cloud IPs).
- Railway (and most PaaS) IPs are frequently 999’d. Guest data is a partial subset.
- You only see what the logged-in member is allowed to see. Private profiles stay private.
- Full-profile decorations have historically capped experience lists (~18 roles). Extra sections are best-effort.
- Guest JSON-LD is missing on many profiles and after an authwall.
- LinkedIn ToS forbid this. Treat it as a take-home / research artifact, not a SaaS.

## License

Use at your own risk. No warranty.
