# Local Flexo SysML v2 service

Glossary, for a reader coming to this cold:

- **Layer 1**: Flexo's core model-management service (org/repo/branch/commit store over RDF), on `:8080`.
- **Quad store (Fuseki)**: the Apache Jena triple/quad database Layer 1 keeps everything in, on `:3030`.
- **SysML v2 API**: the OMG REST API for projects, commits and elements; the `flexo-sysmlv2` service (`:8083`) implements it on top of Layer 1.
- **C1/C2/C3**: three successive full-snapshot commits of a model; the live test publishes them and diffs C1 to C2 and C2 to C3.

Runs the Flexo SysML v2 API on `http://localhost:8083`, backed by Layer 1 (`:8080`) and
Fuseki (`:3030`). Verified 2026-10-14 on Colima/Docker with image
`openmbee/flexo-sysmlv2:v0.2.0` (Layer 1 image `v0.3.0`, Fuseki `4.6`), as shipped in the
upstream compose file; nothing is overridden.

## Interface

```python
FlexoV2(base_url=None, token=None)       # each falls back to FLEXO_V2_URL / FLEXO_V2_TOKEN
.ensure_project(name) -> id
.publish(project_id, elements, message, git_sha) -> commit_id   # raises NoChangeError if identical
.elements(project_id, commit_id) -> {@id: element}
.git_sha(project_id, commit_id) -> str | None                   # the git-<sha> tag of a commit
.head(project_id) -> commit_id                                 # head of the default branch
.delete_project(project_id)                                     # identity-only; frees no space
diff(a, b) -> {"added", "removed", "changed"}                   # raw-value comparison
```

Each Flexo commit is tagged with the Git SHA (`git-<sha>`). `sysml.git_source` provides
`head_sha(path)` and `text_diff(old, new, name)`.

## Bring-up (copy-paste)

```bash
# 1. Clone next to (not inside) this repo
git clone https://github.com/Open-MBEE/flexo-mms-sysmlv2.git
cd flexo-mms-sysmlv2/docker-compose

# 2. Start the three containers (the compose file pins flexo-sysmlv2:v0.2.0; leave it)
docker compose up -d

# 3. Create the Flexo org the SysML v2 service writes into (once per fresh store; Quirks 2)
TOKEN=$(grep '^FLEXO_AUTH=' env/flexo-sysmlv2.env | cut -d= -f2- | tr -d '"')
curl -s -o /dev/null -w "%{http_code}\n" -X PUT http://localhost:8080/orgs/sysmlv2 \
  -H "Authorization: $TOKEN" -H 'Content-Type: text/turtle' \
  --data '<> <http://purl.org/dc/terms/title> "sysml2"@en .'      # expect 201
```

## Auth

- **SysML v2 API (`:8083`): no client token needed locally.** The service authenticates to
  Layer 1 itself with `FLEXO_AUTH` from `docker-compose/env/flexo-sysmlv2.env`, a local
  demo credential that ships in the upstream repo. Do not copy it anywhere; step 3 reads it
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
rerun step 3.

## Stop / start

```bash
cd flexo-mms-sysmlv2/docker-compose
docker compose stop      # stop; keeps containers
docker compose start     # restart; then REPEAT step 3 (the store is empty again)
docker compose down      # remove containers
```

The Fuseki store is in-memory (`--file=cluster.trig`, no TDB volume). **Any restart of
`quad-server` wipes all projects, commits and the org.** Treat the stack as disposable:
bring it up, create the org, publish, and re-publish after a restart.

## Store growth and reset

The store only grows. Measured 2026-10-15 on a store of ~26k quads:

| Operation | Quads added | Time |
|---|---|---|
| `POST /projects` | 89 | 11.5 s |
| first commit of the ADCS model | 5,594 | 10 s |
| each later commit | ~1,950 | 10 s |
| `DELETE /projects/{id}` | -2 | 2.6 s |

Layer 1 materialises `Model.*`, `Load.*` and `Diff.*` graphs per commit, and a project
delete removes only the project's identity, so nothing is reclaimed. After a day of
rehearsals (one project per page load, then) the quad server reached 6 GB and publishes
took 30-40 s.

The deck (`talk.py`) therefore reuses one project per Git SHA (`sysml-talk-<sha7>`): a page
load creates no project, and a snapshot identical to the head reuses the head commit. Each
run of the three demo steps still adds ~6k quads. To start from an empty store:

```bash
bash scripts/flexo_reset.sh   # restart quad-server, wait, re-create the org (step 3)
```

It reads the compose directory from `FLEXO_COMPOSE_DIR` (default: a
`flexo-mms-sysmlv2/docker-compose` checkout next to this repo).

## Notebook environment

```bash
export FLEXO_V2_URL=http://localhost:8083     # default; may be omitted
# FLEXO_V2_TOKEN is optional and unused locally
```

## Tests

```bash
uv run pytest -q tests/test_sysml_flexo.py            # offline: diff(), NoChangeError, git_source
uv run pytest -q -m live tests/test_sysml_flexo.py    # live C1 -> C2 -> C3 round trip
```

## Probed behaviour (what was run, what came back)

| Claim | Result |
|---|---|
| Image v0.2.0 on port 8083 | Held. Compose pins `openmbee/flexo-sysmlv2:v0.2.0`, port 8083; the live test passes on it. |
| `previousCommit` is null | Held. Every commit returns `"previousCommit": null`, although Layer 1 does record a parent for each. Do not use it to walk history; list `/commits` instead. |
| Server-side diff returns 501 | Held. `GET .../commits/{id}/diff` returns `501 Not Implemented`; `diff()` is client-side. |
| No native element delete | Held. Deletion is `?replace=true` (full snapshot: elements absent from the commit disappear) or an identity-only `DataVersion` (no `payload`). Both probed. The client uses `replace=true`. |
| `POST /commits` takes `DataVersion{identity,payload}`; `?replace=true` gives full-snapshot semantics | Held. A second commit of `{A, C}` after a first of `{A, B}` reads back exactly `{A, C}`. |

## Quirks

1. **Commit messages are not stored.** A commit posted with `"description": "git:abc"` reads
   back `"description": ""`, and the quad store holds `mms:message ""`. The Layer 1 source we
   read (not confirmed to match the running v0.3.0 image) does not read `?message=`;
   observed: `mms:message ""`. The API therefore does not expose a commit message here, so each
   Flexo commit is tagged with the Git SHA instead (tag `git-<sha>`; tags read back via
   `GET /projects/{id}/tags`), and `FlexoV2.git_sha()` reads that tag. `publish()` still sends
   `message` as the description, which the stack ignores. Tag names are not unique: two
   commits from one Git SHA yield two tags with the same name.
2. **Fresh store has no org**; `POST /projects` returns 404 until step 3 runs. Same after any
   restart.
3. **Publishing an identical snapshot returns 404** (empty body, no new commit); `publish()`
   raises `NoChangeError("snapshot identical to head")`. Publish only when the model changed.
4. **`@id` handling.** Use UUID `@id`s. Experiments 7-8 saw namespace prefixes stripped from
   non-UUID ids on storage; not re-tested here.
5. **The store performs no type or schema checking.** Any `@type` and any properties are accepted.
6. **Reference arrays (the "owner array" noise).** Properties such as `ownedMember`
   (`[{"@id": ...}]`) and primitive arrays are stored as RDF sets, so the server could in
   principle reorder them. Order preserved in probes (30- and 300-element), so there was no
   observed noise; `diff` compares raw values, and since SysML v2 features such as
   `ownedRelationship` are ordered, a reorder is a real change. Derived reference arrays from a
   real SysML parser (`owner`, `ownedMember`, `ownedElement`) are untested here and are the
   likely source of diff noise. Inverse links (`owner` vs `ownedMember`) are not synthesized by
   the store; each side appears only if you publish it.
7. **`GET .../elements` is not paginated** (300 elements returned in one call; a
   `page[size]` parameter was ignored).
8. Object-valued properties must be pure `{"@id": ...}` references; extra keys inside such an
   object make the commit fail with a `500` (probed).
