# Local Flexo SysML v2 service

Runs the Flexo SysML v2 API on `http://localhost:8083`, backed by Flexo Layer 1 (`:8080`) and
a Fuseki quad store (`:3030`). Verified 2026-10-14 on Colima/Docker.

## Bring-up (copy-paste)

```bash
# 1. Clone next to (not inside) this repo
git clone https://github.com/Open-MBEE/flexo-mms-sysmlv2.git
cd flexo-mms-sysmlv2/docker-compose

# 2. Use the develop-SNAPSHOT image instead of the pinned v0.2.0
#    (develop has the commit-message forwarding fix; see Quirks 1).
sed -i.bak 's#openmbee/flexo-sysmlv2:v0.2.0#openmbee/flexo-sysmlv2:develop-SNAPSHOT#' docker-compose.yml

# 3. Start the three containers
docker compose up -d

# 4. Create the Flexo org the SysML v2 service writes into (once per fresh store; Quirks 2)
TOKEN=$(grep '^FLEXO_AUTH=' env/flexo-sysmlv2.env | cut -d= -f2- | tr -d '"')
curl -s -o /dev/null -w "%{http_code}\n" -X PUT http://localhost:8080/orgs/sysmlv2 \
  -H "Authorization: $TOKEN" -H 'Content-Type: text/turtle' \
  --data '<> <http://purl.org/dc/terms/title> "sysml2"@en .'      # expect 201
```

## Auth

- **SysML v2 API (`:8083`): no client token needed locally.** The service authenticates to
  Layer 1 itself with `FLEXO_AUTH` from `docker-compose/env/flexo-sysmlv2.env`, a local
  demo credential that ships in the upstream repo. Do not copy it anywhere; step 4 reads it
  from that file at run time.
- Layer 1 (`:8080`) needs that bearer token; only the org bootstrap touches it.
- The client reads `FLEXO_V2_TOKEN` (optional) and sends it as a bearer header. The local
  stack ignores it.

## Health check

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8083/projects   # 200 = service up
curl -s http://localhost:8083/projects                                    # [] on a fresh store
```

A `200` only proves the service is up. If `POST /projects` returns `404`, the org is missing:
rerun step 4.

## Stop / start

```bash
cd flexo-mms-sysmlv2/docker-compose
docker compose stop      # stop; keeps containers
docker compose start     # restart; then REPEAT step 4 (the store is empty again)
docker compose down      # remove containers
```

The Fuseki store is in-memory (`--file=cluster.trig`, no TDB volume). **Any restart of
`quad-server` wipes all projects, commits and the org.** Treat the stack as disposable:
bring it up, create the org, publish, and re-publish after a restart.

## Notebook environment

```bash
export FLEXO_V2_URL=http://localhost:8083     # default; may be omitted
# FLEXO_V2_TOKEN is optional and unused locally
```

## Tests

```bash
uv run pytest -q tests/test_sysml_flexo.py            # offline: diff(), git_source
uv run pytest -q -m live tests/test_sysml_flexo.py    # live C1 -> C2 -> C3 round trip
```

## Probed behaviour (what was run, what came back)

| Claim | Result |
|---|---|
| Image v0.2.0 on port 8083 | Held. Compose pins `openmbee/flexo-sysmlv2:v0.2.0`; we switched to `develop-SNAPSHOT` (still port 8083). |
| `previousCommit` is null | Held. Every commit returns `"previousCommit": null`, although Layer 1 does record a parent for each. Do not use it to walk history; list `/commits` instead. |
| Server-side diff returns 501 | Held. `GET .../commits/{id}/diff` returns `501 Not Implemented`; `diff()` is client-side. |
| No native element delete | Held. Deletion is `?replace=true` (full snapshot: elements absent from the commit disappear) or an identity-only `DataVersion` (no `payload`). Both probed. The client uses `replace=true`. |
| `POST /commits` takes `DataVersion{identity,payload}`; `?replace=true` gives full-snapshot semantics | Held. A second commit of `{A, C}` after a first of `{A, B}` reads back exactly `{A, C}`. |

## Quirks

1. **Commit description is dropped on both images (v0.2.0 and develop-SNAPSHOT).** A commit
   posted with `"description": "git:abc"` reads back `"description": ""`, and the quad store
   holds `mms:message ""`. The develop fix forwards the text to Layer 1 as `?message=`, but
   the Layer 1 build in this compose never reads that parameter. **The API does not expose
   a commit message here.** The client therefore also tags each commit `git-<sha>` (tags
   work and read back via `GET /projects/{id}/tags`), and `FlexoV2.git_sha()` reads the
   description first and falls back to the tag. The description is still sent, so it will
   appear if a later server build stores it. Tag names are not unique: publishing two
   commits from one Git SHA yields two tags with the same name.
2. **Fresh store has no org**; `POST /projects` returns 404 until step 4 runs. Same after any
   restart.
3. **Publishing an identical snapshot returns 404** (no change, so no new commit). Publish
   only when the model changed.
4. **`@id` handling.** Use UUID `@id`s. Experiments 7-8 saw namespace prefixes stripped from
   non-UUID ids on storage; not re-tested here.
5. **The store validates nothing.** Any `@type` and any properties are accepted.
6. **Reference arrays (the "owner array" noise).** Properties such as `ownedMember`
   (`[{"@id": ...}]`) and primitive arrays are stored as RDF sets, so the server is free to
   reorder them and collapse duplicates. In 30- and 300-element probes the order came back
   intact and raw equality held, so there was **no observed noise**; `diff()` still compares
   lists as sets so that a future reorder cannot show up as a false `changed`. Corollary: a
   list whose order matters will not round-trip safely. Inverse links (`owner` vs `ownedMember`)
   are not synthesized by the store; each side appears only if you publish it.
7. **`GET .../elements` is not paginated** (300 elements returned in one call; a
   `page[size]` parameter was ignored).
8. Object-valued properties must be pure `{"@id": ...}` references; extra keys inside such an
   object make the commit fail with a `500` (probed).
