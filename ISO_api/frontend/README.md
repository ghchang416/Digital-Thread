# DT Project Creator

Catalog-driven project, workplan, machine, material, file and cutting-tool
authoring with shared operator/detail views, local recovery, CAM import,
NC-only manual authoring and stateless XML generation/validation/download.

The persistent left outline shows instantiated assets and their object hierarchy.
Select a node to edit its values on the right. Search retains ancestors; arrow
keys navigate and Enter selects. On narrow screens the header outline control
opens the tree. Navigation does not change the draft's semantic revision.

Workplan-scoped NX/PowerMill CAM import supports upload/paste, source ordering,
stateless parsing, diagnostics, candidate selection and explicit append. Editing
uses the same outline; imported baselines remain separate from user values.
The legacy CAM endpoint and adapters remain unchanged.

IndexedDB automatically recovers the draft, incomplete numeric inputs, CAM
sources and import state in the same browser profile/origin. Writes use a
sequence check to stop conflicting tabs. Recovery errors preserve old data.
Browser storage is not a durable backup; clearing site data removes recovery.

The sidebar's New Project action opens an explicit reset confirmation. It replaces
the local workspace and clears all stored original blobs in one IndexedDB
transaction. Pending autosaves are invalidated and older tabs cannot overwrite
the new draft. Reset does not delete filesystem originals or backend data.

File assets (NC/STEP/other) retain original Blobs locally and can be assigned to
workplans. NC analysis and explicit step-to-event confirmation create separate
13399 tool assets, keyed by workplan and T number. Repeated T events share one
tool; conflicting current CAM/tool values require a user selection. The existing
legacy NC extractor and 13399 builder are reused without invoking their DB API.
Tools and NC bindings recover with the local draft. The legacy automatic path
synchronizes its five mapped properties and blocks unsupported NC programs.

NC-only authoring registers independent 13399 tools, creates and reorders
workingsteps, and binds tools without CAM JSON. Representative tool types,
properties and units are configured in the backend v31_tools.json profile.
Users confirm NC line ranges and T assignments against the original file;
unsupported NC analysis can use explicit manual confirmation, not automatic
semantic verification. Changed tool values, order or NC evidence require
reconfirmation. Existing CAM bindings switch to manual management only with
explicit consent. Conflicting common tool values require confirmed synchronization.

Manual workingstep creation now has an unchecked authoring-placeholder option.
With consent, the UI prepares the step and completes it before applying either
result to the local workspace. Failure/cancellation leaves the original draft
unchanged. Existing steps use the same manual-aware path from Missing Values.
`POST /workplans/manual-complete` preserves entered values, reconciles missing
standalone 13399/inline tool properties, records completion provenance, and clears
affected NC reviews only when data changes. Conflicting dimensions are never
resolved with placeholders. Unsupported required fields still appear as errors.
The original completion endpoint and existing API schemas remain unchanged.

NC reason checkboxes compose editable reason text only after user selection;
they never acknowledge an NC review automatically. A separate final acknowledgement
remains required. Disabled-button reasons list missing input, tool links, reason
and acknowledgement. XML review highlights placeholders; ZIP reports retain the
warnings. Placeholder XML is authoring-only, not machining-ready.

Machine/material reference selection uses the backend schema profile. Missing
required fields can be completed with explicit authoring placeholders; provenance
and warnings remain available for review. These values are not machining advice.

All-asset review produces a ZIP containing XML, a manifest and a validation report.
Errors or stale confirmations block the complete ZIP. dt_file.value is omitted
with a pending-storage warning until a real storage identifier is available.
No MongoDB/GridFS save, platform publishing, full ISO conformance certification
or machining-safety validation is performed. ZIPs do not include binary originals.
The separate draft JSON download also does not contain original file Blobs.
Three-way reparse merge is not built; duplicate imports are rejected without
overwriting edits. Tool cloning and exhaustive type support remain follow-up work.

## Docker

From the repository root, with the existing iso-api service running:

```sh
docker compose --profile creator build iso-creator-front
docker compose --profile creator up -d --no-deps iso-creator-front
```

Open http://localhost:3011. The port can be changed through CREATOR_FRONT_PORT.
The listener is loopback-only; it is not an authenticated public deployment.
Only the new frontend service is started by the targeted command.

Development override (same service, replaces production mode):

```sh
docker compose -f docker-compose.yaml -f ISO_api/deploy/creator/compose.frontend.dev.yaml --profile creator up -d --build --no-deps iso-creator-front
```

Source is mounted for HMR. The startup command runs npm ci in the frontend-only
dependency volume so a changed lockfile cannot silently retain old packages.
Do not use `down -v` to refresh frontend dependencies: it also risks data volumes.

## Local development

```sh
npm ci
npm run dev
npm run build
npm test
```

Vite listens on port 8080 and proxies /api to localhost:8000. Set the server-only
ISO_API_PROXY_TARGET for a different backend. Never put platform or DB secrets
in VITE_* variables.

The isolated `src.creator_app:app` FastAPI app is for tests/development without
legacy application startup/index creation. Production integration uses the
creator router in src.main, with a request-body limit scoped to creator routes.

## Verification

### Staged ELS Recovery Foundation

ELS remains disabled in the running application. The opt-in storage modules in
`src/features/els/workspace.ts` and `recovery.ts` now support version-2 records,
candidate application, atomic active/previous snapshot swaps and Blob retention.
They are not yet called by the editor or the autosave hook. Active ELS editing
contracts, autosave coordination, source-selection UI and export integration are
still required before enabling the feature. The existing v1 writer refuses ELS
metadata and cannot silently downgrade a v2 active record.

Tests use fake IndexedDB, never the user's browser. To include the cross-language
contract check, generate a synthetic candidate fixture in the backend test
environment (from `ISO_api`, with the output parent already present):

```sh
PYTHONPATH=.:test/creator python test/creator/export_els_recovery_fixture.py frontend/node_modules/els-recovery-fixture.json
```

Then from this frontend directory:

```sh
ELS_RECOVERY_FIXTURE=node_modules/els-recovery-fixture.json npm test
```

Without that environment variable, only the generated-fixture test is skipped.
No backend DB write, platform upload or Access original modification is involved.

### Existing Regression Suites

Backend tests, from ISO_api in an environment with the backend dependencies and
pytest installed:

```sh
python -m pytest test/creator -q
```

The KIMM integration tests need the local demonstration dataset (not committed).
Set KIMM_DATA_DIR to its directory; the default is /data/xml/기계연. Tests requiring
that dataset skip when it is unavailable.

Browser acceptance scripts are test/operator-demo.mjs and test/manual-demo.mjs.
Run them from this frontend directory with PLAYWRIGHT_RUNTIME pointing to a
node_modules directory containing Playwright, Google Chrome installed, and
CREATOR_TEST_URL set to the running frontend URL. They use isolated browser
contexts and the repository's local data/xml/기계연 dataset. Screenshots and ZIPs
are written under the repository outputs directory and are not source artifacts.
