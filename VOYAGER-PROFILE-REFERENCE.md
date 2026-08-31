# LinkedIn Voyager Profile API — Technical Reference (research snapshot, Aug 2026)

Target: a headless Python service that authenticates with an `li_at` session cookie and pulls a
full member profile as JSON, with no browser in the request path.

## Provenance legend

Every claim below carries one of these markers. Nothing here was tested against a live LinkedIn
session by me — I did not have credentials and I deliberately did not probe LinkedIn directly.

| Marker | Meaning |
|---|---|
| **[V]** | Verified from a primary source I read directly: source code, or a live-capture artifact whose author states the date and outcome. |
| **[R]** | Reported by a credible secondary source (issue thread, blog, project README) but not corroborated by code I read. |
| **[U]** | Uncertain / inference. Treat as a hypothesis to test first. |
| **[STALE]** | Documented, but the source predates 2026 and the mechanism is known to rotate. |

Primary sources actually read:

- `linkedin_api` 2.3.1 — full source, extracted from the **PyPI sdist**. The GitHub repo
  `tomquirk/linkedin-api` **now returns 404** (repo removed or made private; the account itself
  resolves). PyPI still serves the package; last release 2.3.1, 2024-11-07, nothing since. **[V]**
- `mguttmann/linkedin-internal-api` — cloned; live captures dated 2026-07 / 2026-08, last commit
  2026-08-01. This is the single most current primary source I found. **[V]**
- `joshuatz/linkedin-to-jsonresume` — cloned; `src/main.js` + `docs/LinkedIn-Dev-Notes-README.md`.
  Last commit 2025-06-22. **[V]** for mechanism, **[STALE]** for specific IDs.
- `openweb` LinkedIn adapter (`src/sites/linkedin/adapters/linkedin-graphql.ts`, `DOC.md`,
  `openapi.yaml`) — read directly. Repo has moved to `imoonkey/openweb`; the
  `openweb-org/openweb` URL 301-redirects there. Last push 2026-06-27. **[V]**
- `EseToni/open-linkedin-api` issue #6 — full comment thread via the GitHub API. **[V]** as a
  record of what practitioners observed.

---

## 1. Is `GET /voyager/api/identity/profiles/{public_id}/profileView` dead?

**Yes. It returns HTTP 410 Gone.** **[V]**

The most precise datapoint: a 2026-07-04 report against a real, valid account states that
`/identity/profiles/{public_id}/profileView` returns a bare `{"status": 410}` **regardless of
session validity** — it is not an auth failure. The same thread has independent 410 reports going
back to 2025-09 (StaffSpy issues #75, #76). **[V]**

The whole legacy `identity/profiles/*` family is being retired, not just `profileView`:

| Legacy endpoint | Observed | Source |
|---|---|---|
| `identity/profiles/{id}/profileView` | **410** | open-linkedin-api #6, 2026-07-04 **[V]** |
| `identity/profiles/{id}/profileContactInfo` | **410** | linkedin-internal-api `docs/20`, verified live 2026-07-12 **[V]** |
| `identity/profiles/{id}/languages` | **410 / 400**, and stale — lagged behind live profile edits by minutes | linkedin-internal-api `docs/BROWSERLESS-REPLAY.md` **[V]** |
| `voyager/api/me` | **200**, still works | linkedin-internal-api (used as the session probe); corroborated in open-linkedin-api #6 **[V]** |

A practical trap worth handling: the 410 body has **no `message` key**. `linkedin_api`'s own error
path does `data["message"]` and throws an unhandled `KeyError`, so the failure isn't even cleanly
catchable in that library. Check `data.get("status")` before touching `message`. **[V]**

### What `profileView` used to return

Preserved here because it is the best available map of "one call, all sections", and it tells you
what you now have to reassemble from several calls. From `linkedin_api/linkedin.py` `get_profile()`
**[V]**, the response was a single object with these sibling view keys, each an
`{"elements": [...]}` collection:

`profile` (with nested `miniProfile`), `positionView` (experience), `educationView`,
`languageView`, `publicationView`, `certificationView`, `volunteerExperienceView`, `honorView`,
`projectView`, `skillView`.

Note `skillView` was capped — the library had a separate `get_profile_skills()` hitting
`/identity/profiles/{id}/skills?count=100&start=0` to get the full list. That endpoint is
presumably also 410 now, but I found no direct confirmation. **[U]**

---

## 2. The modern replacement

There are three distinct surfaces. They are not interchangeable, and one of them is dying.

### 2a. REST: `identity/dash/profiles` with a `decorationId` — the recommended primary read

**This is the highest-confidence working path for third-party profiles in 2026.** **[V]**

```
GET https://www.linkedin.com/voyager/api/identity/dash/profiles
    ?q=memberIdentity
    &memberIdentity=<public_id_slug>
    &decorationId=com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-96
```

Verified as **HTTP 200** by `linkedin-internal-api`, whose `STATUS-MATRIX.md` lists
"Any profile by vanityName | `identity/dash/profiles?q=memberIdentity` | ✅ 200", and whose
`mcp/lib/client.py:163-166` uses exactly this URL with `FullProfileWithEntities-96` as its
`get_profile(vanity_name)`. That client is pure `requests`, no browser. **[V]**

The by-URN variant, also captured live at 200: **[V]**

```
GET https://www.linkedin.com/voyager/api/identity/dash/profiles/urn:li:fsd_profile:<ID>
    ?decorationId=com.linkedin.voyager.dash.deco.identity.profile.FullProfile-76
```

Note the URN is sent **unencoded** in the path segment in the captured sample — colons literal.
**[V]**

#### decorationId catalogue

The trailing integer is a schema version and **increments over time**. Treat it as a moving part.

| decorationId | Version seen | Scope | Confidence |
|---|---|---|---|
| `...identity.profile.FullProfileWithEntities-96` | 96 | Full profile + nested entity collections. The one to start with. | **[V]** live 2026-07/08 |
| `...identity.profile.FullProfile-76` | 76 | Full profile by URN | **[V]** live 2026-07/08; also in openweb `openapi.yaml` as the `getProfileByUrn` default |
| `...identity.profile.FullProfileWithEntities-93` | 93 | Same as -96, older | **[V]** in joshuatz source, **[STALE]** (2025) |
| `...identity.profile.FullProfilePositionGroup-50` | 50 | Grouped positions via `identity/dash/profilePositionGroups?q=viewee&profileUrn=...` | **[V]** in joshuatz source, **[STALE]** |
| `...identity.profile.TopCardSupplementary-128` | 128 | Top card only: name, headline, `publicIdentifier`, and `profileStatefulProfileActions` | **[V]** in a working gist, **[STALE]** (~2023) |
| `...identity.profile.TopCardSupplementary-166` | 166 | Same, newer. Described as the current fallback after `profileContactInfo` went 410 | **[R]** (linkedin-mcp README) |
| `...identity.profile.WebTopCardCore-16` | 16 | Top card core — slug→URN resolution | **[R]** (DeepWiki summary of a Rust client) |
| `...identity.profile.WebTopCardCore-6` | 6 | Same, much older | **[STALE]** (2022 StackOverflow) |
| `...identity.profile.PrimaryLocale-3` | 3 | Locale only | **[STALE]** |
| `com.linkedin.voyager.deco.identity.normalizedprofile.shared.WebApplicantProfile-13` | 13 | `identity/normalizedProfiles/{id}` — applicant-shaped profile | **[V]** captured live 2026 |

**Do not hardcode the version integer.** Two strategies to resolve it at runtime:

1. **Bundle scan.** Regex the JS bundles for
   `com\.linkedin\.voyager\.dash\.deco\.identity\.profile\.FullProfileWithEntities-\d+` and take
   the match. This is the browserless analogue of what joshuatz does in-page. **[U]** — the
   mechanism is sound and the openweb adapter proves bundle-scanning works for queryIds, but I
   found no project doing exactly this for decorationIds.
2. **Version walk.** On a 400/404, try neighbouring integers around your last-known-good.
   Crude but self-healing. **[U]**

For context on why (1) should work: in a browser, joshuatz reads the map directly out of the AMD
module `deco-recipes/pillar-recipes/profile/recipes`, keyed by the *unversioned* recipe name
(`com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities`), which returns the
currently-correct versioned string. That module ships inside the bundles. **[V]**

### 2b. GraphQL `profileCards` — the section data

```
GET https://www.linkedin.com/voyager/api/graphql
    ?includeWebMetadata=true
    &variables=(profileUrn:urn%3Ali%3Afsd_profile%3A<ID>)
    &queryId=voyagerIdentityDashProfileCards.<hash>
```

Called with **only** `profileUrn` and no `sectionType`, this returns the whole set of profile cards
in one response — a working gist parses `about`, `experience`, `education`, and `volunteering` out
of a single call. **[V]** (gist is ~2023, so the shape is **[STALE]** but the calling convention is
corroborated by 2026 captures.)

**Cards are addressed by an entityUrn, and that is where the section-type enum actually lives:**

```
urn:li:fsd_profileCard:(ACoAA...,EXPERIENCE,en_US)
urn:li:fsd_profileCard:(ACoAA...,EDUCATION,en_US)
```

i.e. `(<profileId>, <SECTION_TYPE>, <locale>)`. **[V]** (two independent sources: the gist's
`entityUrn?.includes("EXPERIENCE")` filtering, and a captured-schema document showing the literal
URNs). So to find the experience card you filter `included[]` for an `entityUrn` containing
`EXPERIENCE` — but you must **exclude** `VOLUNTEERING_EXPERIENCE`, which also contains the
substring. The gist does exactly this and it's a real bug source. **[V]**

Section-type values I can attest to, and their casing:

| Value | Where seen | Confidence |
|---|---|---|
| `ABOUT`, `EXPERIENCE`, `EDUCATION`, `VOLUNTEERING_EXPERIENCE` | card `entityUrn` suffixes | **[V]** |
| `SKILLS` | referenced as a card type; the paged component is `SKILLS_VIEW_DETAILS` | **[R]** |
| `CONTENT_COLLECTIONS_DETAILS` | live 2026 capture, as a `sectionType` *param* on `profileCards` (329 KB response) | **[V]** |

**Casing rule — this is a concrete, load-bearing finding.** The two 2026 captures in
`linkedin-internal-api` sit side by side and disagree on case, consistently:

- `voyagerIdentityDashProfileCards` → `sectionType:CONTENT_COLLECTIONS_DETAILS` (**UPPER_SNAKE**)
- `voyagerIdentityDashProfileComponents` → `sectionType:content-collections` (**lower-hyphen**)

And `linkedin_api` 2.3.1 uses `sectionType:experience` (lowercase) against
`profileComponents`. **[V]** So: **`profileCards` takes UPPER_SNAKE, `profileComponents` takes
lower-hyphen.** Getting this backwards is a likely cause of an empty-but-200 response.

I did **not** find an authoritative full enumeration of section types. `certifications`,
`languages`, `courses`, `projects`, `honors` are all plausible by symmetry with the profile UI's
"show all" routes, but I am not going to assert values I did not see. **[U]** Recover the real list
empirically: call `profileCards` with no `sectionType`, then read every
`urn:li:fsd_profileCard:(...)` out of `included[]`. That gives you the exact enum for that
profile, from the server.

### 2c. GraphQL `profileComponents` — "show all" detail pages and pagination

```
GET https://www.linkedin.com/voyager/api/graphql
    ?variables=(profileUrn:urn%3Ali%3Afsd_profile%3A<ID>,sectionType:experience)
    &queryId=voyagerIdentityDashProfileComponents.<hash>
    &includeWebMetadata=true
```

with `accept: application/vnd.linkedin.normalized+json+2.1`. This is verbatim the call in
`linkedin_api` 2.3.1 `get_profile_experiences()`. **[V]** (the hash it hardcodes is long dead — see
§4.)

This maps directly onto LinkedIn's own published architecture. Their engineering blog on
"configurable components" describes cards as a wrapper around an array of component unions, and
says detail screens were unified into "a single API that returns the appropriate list of components
based on the section type passed in". That is `profileComponents`. **[V]**

**Pagination.** The detail views paginate through a distinct entity type:

```
urn:li:fsd_profilePagedListComponent:(<profileId>,SKILLS_VIEW_DETAILS,urn:li:fsd_p...)
```

**[V]** — so the paged-list component URN carries a `<SECTION>_VIEW_DETAILS` discriminator. Beyond
that, use the generic Rest.li paging params `count` and `start`, which Voyager honours broadly and
echoes back in a `paging: {count, start, total}` object at both root and nested levels. **[V]**
Caveat from joshuatz: LinkedIn caps nested element counts on some endpoints, and `total` is often
absent or counts a different granularity than you expect. **[V]**

### 2d. Warning: SDUI is eating this surface

The profile page is migrating to Server-Driven UI (React Server Components) at
`/flagship-web/rsc-action/...`, alongside Voyager. Live captures show
`com.linkedin.sdui.generated.profile.dsl.impl.profileCardsActivity` being POSTed with a payload of
`{"vanityName": "...", "isDetailView": false, "hideProfileCards": false}`. **[V]** One practitioner
in the open-linkedin-api thread reports GraphQL GETs being progressively replaced by SDUI and
describes the result as effectively unparseable. **[R]** openweb dates the jobs-page SDUI migration
to 2026-04 and notes the Voyager GraphQL equivalent still works there. **[V]**

Design implication: keep the extraction layer behind an interface. This surface is actively moving.

---

## 3. Resolving a public slug → `urn:li:fsd_profile:ACoAA...`

Four routes, best first.

**(a) The dash REST call already returns it.** `identity/dash/profiles?q=memberIdentity&memberIdentity=<slug>`
takes the slug directly and its response carries the profile's `entityUrn`. If you're calling it
anyway for the profile body, you get the URN for free — no separate resolution step. **[V]**

**(b) GraphQL by vanityName.** `voyagerIdentityDashProfiles` accepts `(vanityName:<slug>)`
directly:

```
GET /voyager/api/graphql?variables=(vanityName:williamhgates)&queryId=voyagerIdentityDashProfiles.<hash>
```

openweb registers this as its `getProfile` op, maps it to the internal query name
**`web-top-card-core-query`**, and ships a passing example case with
`{"variables": "(vanityName:qi-guo)"}`. **[V]** Confirmed independently as a technique in the
StaffSpy thread. **[V]**

**(c) Top-card decoration + `authorProfileId`.** With
`decorationId=...TopCardSupplementary-128`, the profile id turns up at
`profileStatefulProfileActions.overflowActions[].report.authorProfileId`. **[V]** but **[STALE]**
and fragile — it's reading an id out of a UI action payload.

**(d) Your own URN only:** `GET /voyager/api/me` → `plainId`, `miniProfile.dashEntityUrn`,
`miniProfile.objectUrn`. Still 200 in 2026. Useless for third parties. **[V]**

**Encoding, and it matters:** URNs in `variables` must be **percent-encoded**
(`urn%3Ali%3Afsd_profile%3AACoAA...`), while the Rest.li tuple's own parentheses, colons and commas
must stay **literal**. openweb explicitly builds the URL without encoding the tuple for this
reason; `linkedin_api` uses `quote(profile_urn)` on the URN alone. **[V]** In the `identity/dash/profiles/{urn}`
REST *path*, by contrast, the captured sample has the URN unencoded. **[V]**

---

## 4. Getting `queryId` hashes without a browser

**Do not hardcode them.** LinkedIn pre-registers every GraphQL query at build time and the hash
changes on each frontend deploy — this is stated in LinkedIn's own engineering blog (queries are
registered to a Query Registry Service, "each query has a unique identifier which is generated at
build time") and echoed by every project I read. **[V]**

The `queryName` before the dot is stable; only the 32-hex hash after it rotates.

### The bundle-scan technique — documented and in production

openweb's adapter implements it. This is the real regex, verbatim from
`src/sites/linkedin/adapters/linkedin-graphql.ts:50`: **[V]**

```javascript
/kind:"(?:query|mutation)",id:"(voyager[A-Za-z]+Dash[A-Za-z]+\.[a-f0-9]{32})",typeName:"[^"]+",name:"([^"]+)"/g
```

Capture group 1 is the full `queryId`; group 2 is a human-readable query name. The adapter builds a
`name → queryId` map and caches it for the session. The name it uses for profiles is
**`web-top-card-core-query`**. **[V]**

The algorithm, portable to Python:

1. `GET` a LinkedIn page whose bundles include the queries you want.
2. Extract every `<script src>` pointing at LinkedIn's static CDN.
3. Fetch those bundles (openweb batches 6 at a time) and run the regex over each body.
4. Cache the resulting map; refresh on a 400/404.

**Two gotchas the openweb authors hit and documented:** **[V]**

- **Bundle set is page-specific.** The `full-job-posting-detail-section` queryId appears only in
  the jobs-page bundles, not the feed-page bundles. Expect the same for profile queries — scan a
  profile page, not the feed.
- **Not everything registers as a query.** `voyagerSearchDashReusableTypeahead` is a Rest.li
  service and appears via a name mapping (`SearchDashReusableTypeahead:"voyager..."`), not the
  `kind:"query"` pattern. It won't show up in the scan.

**The bundle URL pattern itself: I could not verify it.** Bundles are served from
`static.licdn.com` **[R]**, but I chose not to fetch LinkedIn to confirm the current path shape,
and no source I read documented it precisely. Don't hardcode a path — parse `<script src>` out of
the page HTML, which is what openweb does and is robust to the pattern changing. **[U]**

Failure signature: openweb reports that a rotated/wrong queryId surfaces as **HTTP 400**;
`linkedin-internal-api` reports **404** for the same condition. Handle both. **[V]**

### Known-real hashes (for smoke tests only — expect them to be dead)

I am **not** inventing any. These were captured live by `linkedin-internal-api` in July 2026 **[V]**:

```
voyagerIdentityDashProfileCards.aec4c2601fac8c5f615c7630b8db1ab3
voyagerIdentityDashProfileComponents.86824295e1093fb0f5acdd8d57213aaa
voyagerIdentityDashProfiles.e9b0809465a07db1f02e70a82d455e10   # variables=(memberIdentity:<id>)
voyagerIdentityDashProfiles.b5c27c04968c409fc0ed3546575b9b7a   # variables=(memberIdentity:<id>) — "top-card variant"
voyagerIdentityDashProfiles.da93c92bffce3da586a992376e42a305   # variables=(profileUrn:urn:li:fsd_profile:<id>)
voyagerIdentityDashProfiles.4be600f2992df8cd036dba7aef973bab   # variables=(profileId:urn:li:fsd_profile:<id>)
voyagerFeedDashProfileUpdates.20c70fe0314184158516a7ec004c0408 # a member's posts
```

Note the three different variable key names across `voyagerIdentityDashProfiles` variants —
`memberIdentity`, `profileUrn`, `profileId`. The hash determines which key is expected. **[V]**

Older, definitely dead, listed only so you recognise them in other people's code:
`voyagerIdentityDashProfileCards.2d68c43b54ee24f8de25bc423c3cf7e4` (~2023) and
`voyagerIdentityDashProfileComponents.7af5d6f176f11583b382e37e5639e69e` (linkedin_api 2.3.1, 2024).
**[V] as historical artifacts.**

---

## 5. The normalized JSON response format

Send `accept: application/vnd.linkedin.normalized+json+2.1` and Voyager flattens the object graph
into two top-level keys. **[V]**

- **`data`** — the "table of contents". Holds the root object plus **references**, not values.
- **`included`** — a flat array of every entity referenced anywhere, each carrying an `entityUrn`.

### Resolution rules

1. Build an index: `{e["entityUrn"]: e for e in response["included"]}`.
2. A key prefixed with `*` holds a URN (or list of URNs) to look up: `data["*elements"]` is an
   ordered array of `entityUrn` strings, and `*profile` is a single reference. **[V]**
3. `$type` on each `included` entry gives its Pegasus schema name, e.g.
   `com.linkedin.voyager.dash.identity.profile.Education`. Filtering by `$type` is the quick way to
   grab all entities of a kind. **[V]**
4. `$recipeTypes` is an array of recipe identifiers describing which decoration shapes produced the
   entity. Present on entities and on `paging` objects. In practice, projects read `$type` and
   ignore `$recipeTypes`. **[V]** — I found no project that branches on it, and no documentation of
   its value space. **[U]**

### The ordering trap — this will bite you

**`included` is not in display order.** joshuatz is explicit: filtering by `$type` alone gets you
entities out of order, and LinkedIn does not put index fields on them. The only way to preserve the
order the user sees on the page is to walk `data["*elements"]` and dereference in sequence. **[V]**
Their `buildDbFromLiSchema` reorders `included` against `*elements` before doing anything else.

A second trap: elements nest. A collection's elements can themselves be
`com.linkedin.restli.common.CollectionResponse` wrappers pointing at further `*elements`. You have
to traverse levels, not flatten. **[V]**

### Concrete example

```json
{
  "data": {
    "$type": "com.linkedin.restli.common.CollectionResponse",
    "*elements": [
      "urn:li:fsd_profileCard:(ACoAAA1B2C3,EXPERIENCE,en_US)",
      "urn:li:fsd_profileCard:(ACoAAA1B2C3,EDUCATION,en_US)"
    ],
    "paging": { "count": 10, "start": 0, "total": 2, "$recipeTypes": ["..."] }
  },
  "included": [
    {
      "entityUrn": "urn:li:fsd_profileCard:(ACoAAA1B2C3,EDUCATION,en_US)",
      "$type": "com.linkedin.voyager.dash.identity.profile.tetris.Card",
      "topComponents": [ /* [0] is the header; [1] holds the list */ ]
    },
    {
      "entityUrn": "urn:li:fsd_profileCard:(ACoAAA1B2C3,EXPERIENCE,en_US)",
      "$type": "com.linkedin.voyager.dash.identity.profile.tetris.Card",
      "topComponents": [ /* ... */ ]
    }
  ]
}
```

`included` here is in the *wrong* order (EDUCATION first). Resolving via `*elements` restores
EXPERIENCE-then-EDUCATION.

```python
def resolve(response):
    index = {e["entityUrn"]: e for e in response.get("included", [])}
    refs = response["data"].get("*elements", [])
    return [index[u] for u in refs if u in index]
```

### Reading a card's contents

Cards are a union-of-components tree. The observed path for a list section: **[V]**

```
card["topComponents"][1]["components"]["fixedListComponent"]["components"][i]["components"]["entityComponent"]
```

and on that `entityComponent`: `title.text`, `subtitle.text`, `caption.text` (dates),
`metadata.text` (location), `image.actionTarget` (company/school URL), with descriptions nested
under `subComponents.components[0].components.{textComponent|insightComponent}.text.text`. Note the
description path differs between experience and education — insight vs text component. **[V]**

`topComponents[0]` is the section header; `topComponents[1]` is the payload. Guard both: the gist
checks `topComponents.length === 0` for empty sections. **[V]**

---

## 6. The exact header set

Consolidated from `lib/vgreq.py` in `linkedin-internal-api` (pure `requests`, verified 200 in 2026)
**[V]**, cross-checked against `linkedin_api/client.py` **[V]** and the openweb adapter **[V]**.

```python
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")

headers = {
    "csrf-token": jsessionid.strip('"'),          # REQUIRED — see below
    "x-restli-protocol-version": "2.0.0",         # REQUIRED for dash/GraphQL
    "accept": "application/vnd.linkedin.normalized+json+2.1",
    "x-li-lang": "en_US",
    "x-li-track": json.dumps({
        "clientVersion": "1.13.45173",
        "mpVersion":     "1.13.45173",
        "osName": "web",
        "timezoneOffset": 2,
        "timezone": "Europe/Berlin",
        "deviceFormFactor": "DESKTOP",
        "mpName": "voyager-web",
        "displayDensity": 1,
        "displayWidth": 1440,
        "displayHeight": 900,
    }, separators=(",", ":")),
    "user-agent": UA,
    "cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
    "referer": "https://www.linkedin.com/feed/",
    "origin": "https://www.linkedin.com",
    "host": "www.linkedin.com",
}
```

### csrf-token derivation

`csrf-token` = the `JSESSIONID` cookie value **with surrounding double quotes stripped**; the
`ajax:` prefix stays. So cookie `JSESSIONID="ajax:1234567890123456789"` → header
`csrf-token: ajax:1234567890123456789`. **[V]**

Two things worth internalising:

- **Missing or malformed `csrf-token` → HTTP 403.** `linkedin-internal-api` is emphatic on this and
  built its whole error taxonomy around it: a 403 means *fix the header*, it does **not** mean the
  session is dead. Their code has a real bug of this shape — `cookies.get("JSESSIONID", "")`
  yielding an empty header and a guaranteed 403. **[V]**
- **CSRF is required on GET too**, which is unusual and catches people out. **[V]**
- `JSESSIONID` is only set after a first page load, so an `li_at`-only cookie jar is not enough.
  **[V]**

### The other headers

- **`x-restli-protocol-version: 2.0.0`** — required. joshuatz notes the GraphQL endpoint in
  particular should always send it. Wrong/absent version breaks certain query-string formats. **[V]**
- **`host: www.linkedin.com`** — joshuatz: omit it outside a browser and you get
  `400 invalid hostname`. Most HTTP clients set it automatically, so this is mainly a raw-socket
  concern. **[V]**
- **`x-li-track`** — the `clientVersion` above (`1.13.45173`) is from a 2026 capture. **[V]**
  Historical values for calibration: `1.13.8953`, `1.12.3124`, `1.2.6216`. To source it live,
  read `<meta name="applicationInstance">` from any LinkedIn page and take `.version`. **[V]**
  I could not determine whether a stale `clientVersion` is actually rejected. **[U]**
- **`x-li-page-instance`** — format `urn:li:page:<pageKey>;<clientPageInstanceId>`, e.g.
  `urn:li:page:d_flagship3_profile_view_base;WCNsJsQPSo63RBfjtgGw3Q==`. The id comes from
  `<meta name="clientPageInstanceId">`; the base64-ish suffix is a per-pageload tracking id. **[V]**
  **Notably, `linkedin-internal-api`'s working 2026 client does not send it at all** and gets 200s.
  So it appears to be telemetry, not auth. **[V]** Send a plausible one if you want to blend in;
  don't treat it as required.
- **`x-li-lang`** — a real quirk: `profileView` always ignored it and returned `defaultLocale`,
  while `/me` respected it. The dash endpoints ignore it too, but instead return parallel
  `multiLocaleFirstName: {"ru_RU": ..., "en_US": ...}` keys you can read directly. **[V]**

---

## 7. Rate limiting, blocking, and whether `curl_cffi` saves you

### Status codes and what they mean

| Signal | Meaning | Confidence |
|---|---|---|
| **403** | `csrf-token` missing/malformed. **Not** session death. | **[V]** |
| **410** | Endpoint retired (the legacy `identity/profiles/*` family). Permanent. | **[V]** |
| **400** | Malformed Rest.li tuple, bad URN form, or a rotated queryId. | **[V]** |
| **404** | Rotated queryId (the other reported signature). | **[V]** |
| **3xx → `Location: /uas/login`** | **The one true session death.** Compare the parsed **path**, not a substring — `/feed/?next=/uas/login` is not a login redirect. | **[V]** |
| **429** | Rate limited. | **[R]** — the endpoint-level 429 is widely reported, but `linkedin-internal-api` explicitly logs it as *anticipated, never observed* in their own operation. |
| **999** | Edge-level "Request Denied", before the app layer. Triggered by non-browser user agents, request volume from one IP, datacenter/cloud IP ranges, robots.txt violations. Automatic and temporary. | **[R]** |
| **200 with an HTML interstitial** | The nastiest one. `linkedin-internal-api` treats a 200 whose body isn't parseable JSON as a failure, precisely to avoid reporting a login interstitial as a healthy session. Do the same. | **[V]** |

Also: LinkedIn rate-limits **tab/page opens independently of API calls** — reported as 429 on the
6th tab within 10 seconds regardless of API volume. Irrelevant to a pure-HTTP service, but it means
rate-limit anecdotes from browser-driven tools don't transfer. **[R]**

### Reported-safe rates

All **[R]** — nobody publishes measured thresholds, these are practitioner numbers.

| Source | Guidance |
|---|---|
| `linkedin_api` 2.3.1 | `sleep(random.randint(2, 5))` before **every** request; a hard cap of 200 repeated requests. **[V]** as code. |
| linkedin-mcp | Daily caps: 80 profile views (defaults), ~100–150 is LinkedIn's actual ceiling. New accounts (<30d): 40/day. |
| A 2026-04 capture harness | Gaussian delay, mean 1.5 s, between calls. |
| General 2026 guidance | 50–100 profiles/day on an aged account + residential IP; >100–150/hr from one session is a ban trigger. |

Exceeding these gets the account "feature-restricted" for 24–72 h rather than returning an error
code. Budget for that failure mode.

### Does PerimeterX TLS fingerprinting block plain `requests`?

**The sources genuinely conflict, and the conflict is informative.** I'll give you both.

**Evidence it does NOT block you** — the strongest single piece of evidence I have, because it's a
2026 project built on exactly your architecture: **[V]**

`linkedin-internal-api` runs all Voyager calls through plain `requests`
(`lib/vgreq.py`, `allow_redirects=False`) and gets 200s. Their `01-AUTH-AND-COOKIES.md` documents
having chased this exact question and concluded the opposite of the folklore:

> **Historical pitfall:** early tests against `/voyager/api/me` returned a 302 redirect loop → we
> wrongly suspected bot detection / fingerprinting. The real cause: the cookies were **expired**.
> With **fresh** cookies the pure HTTP path works fine. **Browser fingerprint plays NO role.**

The browser in their design exists *only* to mint cookies. Everything after is `requests`.

**Evidence it DOES block you** — three independent reports: **[R]**

- linkedin-mcp: "Direct Node.js `fetch()` to Voyager is blocked by TLS fingerprint check → all
  requests redirected with `li_at=delete-me`."
- open-linkedin-api #6: a lifted cookie jar carries PerimeterX fingerprint cookies (`_px3`,
  `pxcts`, `dfpfpt`, `fptctx2` on `protechts.net`) bound to the originating browser. A `requests`
  session replaying them got **401 on `/me` within about a minute** of a successful first call —
  "cookie-lifting buys you a login, not necessarily a durable session."
- devag7/linkedin-mcp: a stateless `fetch`/`curl` "gets stuck in an endless redirect, even with a
  valid cookie."

**My reading of the conflict.** The reports are compatible if the discriminator is **which cookies
you carry and how fresh they are**, not the TLS handshake. `linkedin-internal-api` dumps the *whole*
cookie jar via CDP `Network.getAllCookies` — including the PerimeterX cookies — and refreshes it
with a daemon. The failures describe partial cookie sets, or PerimeterX cookies going stale against
a mismatched fingerprint. That is a coherent story, and it's **[U]** — I can't prove it.

**On `curl_cffi` with `impersonate="chrome"`:**

- It reliably fixes the **TLS/JA3 and HTTP/2 framing layer**. That much is uncontested. **[V]**
- It is **not sufficient in general for PerimeterX**, which layers behavioral biometrics on top of
  passive fingerprinting. A 2026 bypass guide is specific about LinkedIn: PerimeterX loads via a
  hidden 0×0 iframe from `li.protechts.net` that sets `_px3`/`_pxhd`/`_pxvid`/`_pxcts` over
  cross-origin postMessage — invisible in main-page traffic, and requiring JS you cannot execute.
  **[R]**
- But at least one 2026-04 capture harness reports success: *"PerimeterX protection bypassed via
  curl_cffi Chrome TLS impersonation"*, with one specific operational note — **do not set a custom
  User-Agent, because `curl_cffi` injects a matching Chrome UA via impersonation** and an
  inconsistent UA/TLS pair is itself a signal. **[R]**

**Recommendation.** Use `curl_cffi` with `impersonate="chrome"` — it's a drop-in for `requests`,
costs nothing, and removes one whole detection layer. Do **not** expect it to be the thing that
makes this work. The load-bearing parts are (1) the full cookie jar including PerimeterX cookies,
(2) keeping it fresh, and (3) a residential IP. Datacenter IPs are pre-flagged. **[R]**

Also note LinkedIn runs an extension/hardware fingerprinting script (scans for 6,000+ Chrome
extensions), the results of which are reportedly encrypted into a request header. **[R]** If a
required header is derived from that, a headless client can't produce it — a risk worth an early
spike, though nothing I read says any *profile read* endpoint currently requires it.

---

## 8. Building media URLs

Simple concatenation, no encoding step. **[V]**, corroborated across four independent codebases.

```
final_url = vectorImage["rootUrl"] + artifact["fileIdentifyingUrlPathSegment"]
```

`rootUrl` ends with a trailing separator and `fileIdentifyingUrlPathSegment` begins with the size
prefix, so plain string concatenation is correct.

```json
{
  "com.linkedin.common.VectorImage": {
    "rootUrl": "https://media.licdn.com/dms/image/C5103AQEJ4t5ijWZ8Xg/profile-displayphoto-shrink_",
    "artifacts": [
      {"width": 200, "height": 200,
       "fileIdentifyingUrlPathSegment": "200_200/0/1516745437487?e=1619049600&v=beta&t=66x3s8Hw...",
       "expiresAt": 1619049600000},
      {"width": 400, "height": 400, "fileIdentifyingUrlPathSegment": "400_400/0/...", "expiresAt": 1619049600000},
      {"width": 800, "height": 800, "fileIdentifyingUrlPathSegment": "800_800/0/...", "expiresAt": 1619049600000}
    ]
  }
}
```

Concatenating gives:

```
https://media.licdn.com/dms/image/C5103AQEJ4t5ijWZ8Xg/profile-displayphoto-shrink_800_800/0/1516745437487?e=1619049600&v=beta&t=YW7bUQO8...
```

```python
def build_media_url(vector_image, largest=True):
    if not vector_image or not vector_image.get("artifacts"):
        return None
    arts = sorted(vector_image["artifacts"], key=lambda a: a["width"], reverse=largest)
    return vector_image["rootUrl"] + arts[0]["fileIdentifyingUrlPathSegment"]
```

Notes:

- **The `t=` signature is per-artifact.** Each width has its own signed token, so you cannot take
  the 200×200 segment and rewrite it to `800_800`. Pick the artifact you want and use its segment
  whole. **[V]**
- **URLs expire.** `expiresAt` is epoch **milliseconds**; `e=` in the query is epoch **seconds**.
  Persist `expiresAt` alongside the URL, or download the bytes. **[V]**
- **`rootUrl` host has changed before** — older captures show `media-exp1.licdn.com`, current ones
  `media.licdn.com`. Never reconstruct the host; always take `rootUrl` from the response. **[V]**
- **Background/cover images** use the same `VectorImage` shape under a different key
  (`backgroundImage` / `profileBackgroundImage`), with `profile-displaybackgroundimage-shrink_` in
  the `rootUrl`. **[U]** — same structure, but I did not see a captured example.
- **Legacy vs dash wrapping differs.** The legacy shape nests under the literal key
  `"com.linkedin.common.VectorImage"`; dash/GraphQL responses tend to expose the vector image
  directly. Handle both. **[V]**
- Some entries carry a plain `imageUrl.url` instead of a vector image — fall back to it. **[V]**

---

## 9. Suggested implementation path

1. **Cookies.** Get `li_at` **and** `JSESSIONID`. Ideally dump the whole jar (including
   `_px3`/`bcookie`/`lidc`) from a real logged-in browser once, e.g. via CDP
   `Network.getAllCookies` after loading `/feed/` (JSESSIONID isn't set until then). Refresh
   periodically.
2. **Transport.** `curl_cffi` with `impersonate="chrome"`, `allow_redirects=False` (you need to see
   the 302 to classify session death), and no custom User-Agent.
3. **Bootstrap.** `GET /voyager/api/me` as a session probe. Classify strictly: healthy means 2xx
   **and** a parseable JSON object body.
4. **Resolve.** `identity/dash/profiles?q=memberIdentity&memberIdentity=<slug>&decorationId=...FullProfileWithEntities-96`
   → profile body plus `urn:li:fsd_profile:...` in one call.
5. **Sections.** `graphql?variables=(profileUrn:<encoded>)&queryId=voyagerIdentityDashProfileCards.<resolved>`
   with no `sectionType` first — enumerate the real card types from the returned
   `urn:li:fsd_profileCard:(...)` URNs rather than guessing the enum.
6. **Detail/pagination.** For sections that are truncated, `voyagerIdentityDashProfileComponents`
   with the **lower-hyphen** `sectionType` and `count`/`start`.
7. **queryId resolution.** Implement the bundle scan (§4) with a cached map and automatic refresh
   on 400/404. This is the single highest-value piece of resilience in the whole design.
8. **Parsing.** Index `included` by `entityUrn`; always traverse via `*`-prefixed reference keys to
   preserve order.
9. **Pacing.** 2–5 s jittered between requests, well under 100 profiles/day per account, residential
   IP.

## 10. Biggest open questions

- The complete `sectionType` enum for `profileCards` / `profileComponents` — recover empirically.
- Whether the bundle-scan approach works for **decorationId** versions the way it does for
  queryIds. Untested, but the strings are in the bundles.
- The current `static.licdn.com` bundle path pattern — parse it from page HTML rather than
  hardcoding.
- Whether plain HTTP survives *durably* or only for a first burst. The 401-within-a-minute report
  and the "pure requests works fine" report are both from credible sources. Instrument for it and
  find out on your own account before you build on the answer.
- How fast SDUI swallows the profile page. This is the strategic risk, not the tactical one.
