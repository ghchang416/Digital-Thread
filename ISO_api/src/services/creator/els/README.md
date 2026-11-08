# ELS Inspection and Staged DT Generation (G1 / G2a / G2b)

Status, 2026-10-30: owned source inspection and a representative staged DT/XML
generation flow are implemented. Active workspace application and the ELS user
interface are **not enabled**. DB persistence and platform upload are out of scope.

## Boundaries

- `src/schemas/creator_els.py`: strict candidate DTOs, one PART/revision/OP/program
  selection, source rows stored once, field origins, ELS-owned steps/tools/reviews
  and metadata-only files. IDs and source keys are separate. Large exact numbers
  use strings at the JavaScript boundary.
- `profile.py` and `profiles/els_milling_v1.json`: ELS-only hashed rules, validated
  against the current model catalog. Different numeric candidates require an
  explicit choice. Zero/false/NULL/empty values are not silently conflated.
  Optional spindle/feed values are not made model-required. Coverage distinguishes
  the tested staged milling template from deferred operation/machine types.
- `tool_identity.py`: source-only tool grouping within one selected OP/program.
  Same T with different configuration is a conflict. Missing identity cannot be
  invented by assigning equal placeholders. Missing configuration requires an
  explicit per-row operator configuration ID and reason. No Tool_Milling fuzzy match.
- `contracts.py`: pure preflight for ownership, source links, graph depth/expansion,
  and UTF-8 request budgets. Append-tools cannot modify existing nodes, assets,
  file bindings, NC reviews, assignments or source history. Replacement needs a
  fresh draft ID; both modes require the correct base ID/revision.
- `GET /api/v3/creator/els/capabilities`: read-only feature discovery. Always returns
  `enabled:false` at this stage, even when `CREATOR_ELS_ENABLED=1` and Java/JAR is
  present. Runtime presence is not full importer readiness. `inspectionEnabled`
  reports only the upload/catalog runtime gate. `stage:staged-vertical` indicates
  the separate candidate APIs, not active UI/application readiness.

## Temporary Inspection API (G2a)

These new paths do not accept or change CreatorDraft, NC reviews, browser records,
MongoDB, or GridFS. No database startup/lifespan is required for their tests.

| Method/path, under `/api/v3/creator/els` | Contract |
| --- | --- |
| `POST /imports` | Exactly one multipart `file`; `X-ELS-Request-Id` header (1-128 ASCII letters/digits/underscore/hyphen). Returns 202, `importId`, a secret `ownerToken`, status and expiry. |
| `GET /imports/{id}` | Upload/read/ready/failed status, source hash, table counts and sanitized error code. Never returns the owner token again. |
| `GET /imports/{id}/operations` | PART/revision/OP summaries, optional `search`, `cursor`, `pageSize` (1-100). |
| `GET /imports/{id}/operations/{key}` | OP summary/issues and paginated program/revision summaries; does not inline all machining rows. |
| `GET /imports/{id}/operations/{key}/programs/{programKey}/rows` | Paginated source rows in SEQ order, preserving original T numbers, exact numbers and conflict diagnostics. |
| `GET /imports/{id}/diagnostics` | Paginated source schema/relationship diagnostics. |
| `DELETE /imports/{id}` | Cancels queued/active reading, waits for reader cleanup, removes temporary files and memory; 204. Does not delete any draft. |

Every per-import path requires `X-ELS-Owner-Token`. Missing, wrong, cancelled,
expired and unknown sessions return the same 404. Tokens belong in headers, not
URLs, logs or persistent draft metadata. Successful responses use `no-store`.
`requestId` is a correlation identifier, not an idempotency/recovery credential.
After a lost creation response, that orphaned session expires; reselect the file.

Runtime gate: `CREATOR_ELS_ENABLED=1` and an available Java/JAR reader. The shared
backend's environment and Java installation have **not** been changed. Missing
runtime/config returns 503 only for inspection; existing generation remains usable.
The capability `enabled:false` still prevents advertising complete ELS generation.

- Reader work runs in one bounded background executor, not the ASGI event loop.
- Maximum 4 sessions; 15-minute fixed TTL; cleanup sweeps every 5 seconds.
- Capacity is reserved before multipart parsing: 3 copies of the maximum file size
  per pending upload/read (parser spool, source, reader copy), within a 768 MiB
  temporary disk budget. At default 128 MiB files this admits two pending jobs.
  Ready/failed sessions release disk reservations but still count toward four.
- Upload timeout is 120 seconds. Reader time/output/row/process limits still apply.
- Only `POST /els/imports` has the streaming body cap of 128 MiB + 64 KiB multipart
  overhead; file bytes are separately capped at 128 MiB. All other middleware
  branches/limits are unchanged, including the 2 MiB `/nc/confirm` limit.
- Byte-bounded pages retain a next cursor rather than dropping rows. Source
  snapshots are not automatically latest-selected, merged, mapped or corrected.
- Private temp root defaults to `/tmp/dt-creator-els-imports`, configurable with
  `ELS_IMPORT_TEMP_ROOT`. An exclusive root lease prevents competing process owners.
  This implementation supports one inspection owner per root; another API worker
  receives `IMPORT_STORE_BUSY` instead of silently routing to a different session.
  Multi-worker session routing/shared storage is not implemented.
- A restarted owner removes only marked abandoned ELS directories after acquiring
  the lease. Active owners and unrelated directories are never cleared. Reader
  scratch files live inside the session directory. Source bytes are removed as
  soon as reading finishes. Remaining indexes live only in process memory.
- Expiring/cancelled uploads retain their capacity until the request's parser is
  closed. Disconnect, timeout, malformed/truncated multipart, and size rejection
  close spools and release the reservation; cancellation waits for child reaping.

The returned source data is inspection output, **not** a valid DT candidate or
evidence confirmation. Explicit staged preparation/confirmation follows below.
UI selection/apply and format-2 recovery remain subsequent gates. No new server
container is required.

## Staged Milling Candidate API (G2b)

| Method/path, under `/api/v3/creator/els` | Contract |
| --- | --- |
| `GET /imports/{id}/operations/{key}/programs/{programKey}/source` | Owned, bounded source context for explicit choices: related part/OP/machine/file rows and program rows. |
| `POST /imports/{id}/prepare` | `ElsBuildRequest`: base draft, prepare command, OP/program keys, identity defaults, explicit decisions. Returns a separate candidate plus per-asset checks, never updates the base. Rechecks session ownership/expiry after construction. |
| `POST /complete` | Candidate and owned WP ID, `includePlaceholders` and `synchronizeTools` opt-ins. Missing-only completion; conflicting internal tool values require explicit synchronization. |
| `POST /confirm` | Candidate, WP IDs and explicit acknowledgement. Validates authoring completeness and creates scoped state hashes; not source authentication or NC confirmation. |
| `POST /review` | Candidate and 1-10 target asset IDs. Returns XML artifacts, model/roundtrip diagnostics, origins, explicit decisions and pending-storage warnings. |

Preparation uses the owned source session; complete/confirm/review are stateless
candidate operations that remain usable after the source session is deleted.
They do not prove that a submitted snapshot is an authentic external document.
All successful responses are `no-store`. Prepared XML checks do not return XML;
the review route is the artifact response. Browser ZIP download is not connected yet.

- `replace-project` produces a **new candidate**, main WP -> one OP/program WP ->
  ordered steps, one real project Workpiece, basic material/machine references,
  separate 13399 tools and explicitly selected metadata-only files.
- `append-tools` adds only independent 13399 assets/definitions to a copied legacy
  base. Existing nodes, file links, NC reviews and assignments are unchanged.
- The first template is `FreeformOperation + ToolpathFeature + MillingCuttingTool`.
  It requires explicit milling/template acknowledgement and rejects known turning
  operations. It does not infer detailed machining strategies or machine axes.
- Same T with different source configurations is rejected. Equal placeholders
  never establish identity. Numeric conflicts, diameter candidates, excluded rows
  and reordered/ambiguous sequences require explicit choices/reasons.
- Spindle rpm -> 1/s and feed mm/min -> m/s are converted once. Source snapshots
  retain other conditions; the review warns about unrepresented selected candidates.
- Existing completion and manual-tool services are reused without changing them.
  Source/manual/default/placeholder provenance stays in the separate ELS metadata.
  Completion preserves existing values, uses the real project Workpiece, and
  invalidates changed ELS confirmations instead of manufacturing NC evidence.
- A WP hash covers its source selection, reachable graph, used tool definitions,
  referenced material/machine, metadata files and rule hashes. Unused tools are
  excluded. Changes require re-confirmation. This is consistency, not a digital
  signature or external-source authentication.
- The ELS resolver checks the original graph, then calls the existing resolver.
  Legacy NC errors remain blocking. Only validated ELS slots receive derived tool
  references; metadata-only file exceptions omit **only** `dt_file.value`.
  Paths are never fetched. Reports explicitly state that original bytes are absent.
- Every artifact remains authoring-review-only, `finalizable:false`,
  `machineReady:false`, `persisted:false`. XML validation is model metadata plus
  xsdata roundtrip, not XSD certification, NC execution or machining safety.

## Deliberate Staging Decision

`ElsCandidate` contains the existing `CreatorDraft` plus a separate `ElsMetadata`
object. The active CreatorDraft and existing XML APIs still reject ELS extension
fields. This prevents an incomplete ELS graph from bypassing legacy NC rules or
being saved without its provenance. Candidate validation is not confirmation,
source authentication, semantic machining validation, or XML validation.

The G2b resolver is deliberately limited to a separate candidate. Wire the
extension into active DTOs only together with editing guards. In G3, apply it
only through a format-2 recovery transaction that
preserves previous workspace/Blobs with sequence CAS. Do not call an existing
`applyPrepared(candidate.draft)` or `saveRecovery` to apply this staged result.
The current v1 reader/writer rejects nonempty ELS fields instead of discarding them.
The API draft version, recovery-record version and IndexedDB schema version remain
separate contracts. No real user workspace was used for migration tests.

## NC Signature Compatibility

The frontend now signs only the tool definitions used by the selected manual WP.
The previous algorithm remains available solely for verifying an existing stored
signature. Recovery migrates it only after workspace/Blob validation and only if
it still matches the previous algorithm for that exact data. Already-stale
signatures remain stale; unconfirmed sessions remain unconfirmed. The source
record is not mutated and no immediate IndexedDB write occurs on reading.

CAM signature behavior and server manual confirmation hashes are unchanged.
Existing schema hash, reference policy hash, rulesVersion and v31_tools profile
are unchanged. New confirmation strings can appear stale in an older frontend;
rolling back does not fabricate confirmation or remove draft data.

## Budgets and Coverage

- Active API body cap remains 2 MiB. Candidate draft+metadata budget is 1.75 MiB,
  reserving 256 KiB for request-specific fields. Call `check_request_budget` on
  every complete envelope before later integration, not just on the bare draft.
- Existing limits: 10,000 nodes, 1,000 assets, 20,000 completion entries, 300 direct
  steps, depth 64 and 10,000 expanded visits per asset. Candidate preparation does
  not silently truncate or split over-limit input.
- Tested staged vertical: FreeformOperation + ToolpathFeature + MillingCuttingTool,
  basic MachineTool, Material, NumericalValue and Unit, with graph completion,
  13399/internal-tool synchronization and model XML roundtrip.
- Detailed controllers, axes/spindles and other operation/tool combinations are
  declared deferred until their required children and roundtrip tests are covered.

## Verification

From the running Python 3.10 backend environment:

```sh
python -m pytest -q -p no:cacheprovider test/creator
```

Frontend: `npm test` and `npm run build` in `ISO_api/frontend`.
The focused tests are `test/creator/test_els_contracts.py` and the NC compatibility
tests in `frontend/test/manual.test.ts`. Existing regression suites remain enabled.

Verified 2026-10-30: backend 202 passed / 9 reader-runtime skips; those runtime
tests ran in the isolated MDB/ACCDB suite (35 passed). G1 contributes 50 backend
tests. Frontend 65 passed (11 new compatibility tests) and TypeScript/Vite build
passed. Existing deprecation warnings remain. No production frontend image was
replaced, and no commit/push was made.

G2a verification: 30 session/API/limit/ownership tests; the actual Access reader,
catalog and new session integration tests pass together (37 tests) in the existing
one-shot reader test image. A full production-app OpenAPI comparison against HEAD
preserves all 57 existing path definitions and all existing component schemas.
Application startup/DB writes and optional MCP initialization are excluded from
that contract audit. This is not a legacy upload/write end-to-end certification.
Full creator backend regression: 232 passed / 11 reader-runtime skips (covered by
the one-shot reader suite); frontend 65 passed, TypeScript/Vite build passed.

G2b verification: **265 passed / 13 reader-runtime skips** in the shared backend,
including existing real KIMM CAM/NC and manual NC acceptance. A read-only, networkless
one-shot Java+backend test image ran **276 passed / 2 skips**; those two are the KIMM
tests whose external `/data` mount is absent there. All 13 reader-runtime tests,
including actual synthetic MDB/ACCDB -> source selection -> candidate -> confirmation
-> five model XML artifacts, pass in that image. The new vertical suite has 35 tests.
No production runtime/Java/flag/image change or additional API server was made.

Frontend remains **65 passed**, TypeScript/Vite build passed. Existing 57 production
OpenAPI paths and component definitions remain unchanged against HEAD, with DB
access blocked and lifespan/optional MCP excluded. `GET /schema` and ELS capability
both return 200 on the running shared server; ELS is still disabled there because
the runtime/flag and full UI/recovery integration are not ready.

One-shot reproduction, after building the G0 reader test image and using the local
backend image containing test dependencies:

```sh
docker build --network none -f deploy/creator/Dockerfile.els-vertical-test -t dt-els-vertical-test:local .
docker run --rm --network none --read-only --tmpfs /tmp:size=512m --cpus 1 --memory 768m \
  -v "$PWD:/app:ro" dt-els-vertical-test:local \
  /opt/conda/envs/myenv/bin/python -m pytest -q -p no:cacheprovider test/creator
```

Next: operator source/choice UI, candidate inspection and download controls, active
DTO/edit guards, format-2 atomic application/restore, then browser E2E. Staged
replacement has revision zero; active edit revisions are a separate G3 contract.
Mixed legacy/ELS WP confirmation/editing and appending to an already-active ELS
workspace are not claimed complete. Real customer Access and detailed machine/
strategy mappings also remain unverified. Do not apply only `candidate.draft` and
discard ELS metadata.

## G3a-1 Local Storage Foundation (2026-10-30)

The frontend now has opt-in format-2 workspace and transactional recovery modules.
They preserve ELS metadata separately from the unchanged CreatorDraft, snapshot
unsaved legacy inputs/Blobs on replacement, retain existing data on append-tools,
and atomically swap one previous slot on restore. Legacy recovery fails closed
for ELS data. These modules are **not connected to the editor/autosave hook**;
active DTO/edit guards, queue integration, source UI and export remain required.
Capability and shared-server runtime settings are unchanged.

Frontend verification: 89 passed with a generated synthetic backend candidate
fixture, including 22 new storage/contract tests; TypeScript/Vite build passed.
`test/creator/export_els_recovery_fixture.py` exports real prepare/confirm results
for that opt-in test. No real browser data or server database is used. This does
not certify real customer Access compatibility or active browser E2E readiness.
