# Flexo MMS integration

The demo's persistence layer can push the RTM Dataset into a real Flexo
MMS instance — proving the named-graph quadstore layout we designed in
Phase C composes with the production-grade JPL / OpenMBEE tooling.

**Default target: the shared remote Flexo at
[try-layer1.starforge.app](https://try-layer1.starforge.app).** This is
the collaboration target — running the demo against the same remote as
your collaborators makes their state visible to you (and yours to them).
Local Compose is supported as an alternative for offline development.

## Default path — remote starforge

Prerequisite: a bearer token for `try-layer1.starforge.app` (request
from a collaborator who has access).

```bash
export FLEXO_TOKEN="eyJhbGci..."          # token from your collaborator
./flexo/init.sh                            # one-time: PUT org + repo + master
uv run python -m pipeline.runner --auto --backend=flexo
```

That's it. Stage 7 will create per-named-graph branches in
`adcs-demo/lifecycle` and load each named graph via SPARQL
`INSERT DATA` POSTs.

The runtime uses `FLEXO_TOKEN` directly — no `/login` call needed for
pre-authenticated remote instances. See *Inspecting the result* below
for how to query the loaded data.

## Alternative path — local Compose

For offline work, the [flexo-mms-deployment](https://github.com/openmbee/flexo-mms-deployment)
repo provides a `docker-compose` configuration that brings up the
entire Flexo stack (Layer1 + auth + Fuseki + MinIO + OpenLDAP) locally:

```bash
git clone https://github.com/openmbee/flexo-mms-deployment.git
cd flexo-mms-deployment/docker-compose
docker compose up -d
# wait for: "layer1-service | ... Responding at http://0.0.0.0:8080"
```

Point the demo at the local stack instead of the remote:

```bash
export FLEXO_URL=http://localhost:8080
export FLEXO_AUTH_URL=http://localhost:8082
unset FLEXO_TOKEN                          # forces login flow
# defaults: FLEXO_USER=user01 / FLEXO_PASS=password1
./flexo/init.sh
uv run python -m pipeline.runner --auto --backend=flexo
```

On Apple Silicon, Flexo images are `linux/amd64` and run under QEMU
emulation. Expect 3-10× slower cold starts; Fuseki allocates an 8 GB
Java heap which is slow to initialize the first time.

## One-time provisioning

`flexo/init.sh` is idempotent and works against either target. It:

1. Auths (uses `FLEXO_TOKEN` if set, otherwise calls `/login` on
   `FLEXO_AUTH_URL`).
2. Idempotently PUTs the `adcs-demo` org and `lifecycle` repo.
3. Idempotently PUTs the `master` branch.

Subsequent pipeline runs create per-named-graph branches automatically.

## Inspecting the result

```bash
# List branches in the adcs-demo repo
curl -H "Authorization: Bearer $FLEXO_TOKEN" \
  "$FLEXO_URL/orgs/adcs-demo/repos/lifecycle/branches"

# Query a specific branch (e.g. attestations)
curl -X POST -H "Authorization: Bearer $FLEXO_TOKEN" \
  -H "Content-Type: application/sparql-query" \
  "$FLEXO_URL/orgs/adcs-demo/repos/lifecycle/branches/attestations/query" \
  --data-binary 'SELECT * WHERE { ?s ?p ?o } LIMIT 10'
```

## Teardown

```bash
./flexo/teardown.sh
# or
make flexo-down
```

Deletes the `adcs-demo` org and all its repos/branches from your Flexo
target. For local Compose, also run `docker compose down` in the
deployment repo to shut down the stack itself.

## Configuration via environment

| Variable | Default | Notes |
|---|---|---|
| `FLEXO_URL` | `https://try-layer1.starforge.app` | Layer1 REST API |
| `FLEXO_TOKEN` | (unset) | **Required for the remote default.** Pre-issued bearer; skips login. |
| `FLEXO_AUTH_URL` | `http://localhost:8082` | Only used when `FLEXO_TOKEN` is unset (login flow) |
| `FLEXO_USER` | `user01` | Login flow username |
| `FLEXO_PASS` | `password1` | Login flow password |
| `FLEXO_ORG` | `adcs-demo` | Org slug |
| `FLEXO_REPO` | `lifecycle` | Repo slug |

To avoid clobbering a collaborator's state on the shared remote, set
`FLEXO_REPO=lifecycle-${USER}` or similar before running.

## No-Docker fallback

If you can't run Compose and don't have a remote token, use the bare
Apache Jena Fuseki backend — it still validates the named-graph layout
against a real quadstore, just without Flexo's branch / commit / auth
semantics:

```bash
docker run -d --name fuseki -p 3030:3030 stain/jena-fuseki
uv run python -m pipeline.runner --auto --backend=fuseki
```
