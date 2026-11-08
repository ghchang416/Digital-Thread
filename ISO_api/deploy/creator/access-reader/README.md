# ELS Access Reader Foundation

Status: isolated reader/catalog implementation, **not an enabled generator feature**.
The G0 reader itself does not change the active draft, model_v31, CAM parser or
storage paths. The subsequent G1 contract/NC compatibility work is documented in
`src/services/creator/els/README.md`; it adds a disabled capability endpoint and
frontend signature migration without enabling ELS import.

## What Is Implemented

- Read-only table/schema/primary-key extraction using Jackcess 4.0.8, Java 17.
- Python 3.10 adapter in `src/services/creator/els/reader.py` with bounded NDJSON,
  exact decimal decoding, input hash, timeout/cancellation and temporary cleanup.
- Explicit V2000 (MDB) and V2010 (ACCDB) format allowlist. Other formats fail closed.
- Eight ELS tables only. No SQL, saved queries, macros, VBA, or linked-file access.
- PART/revision/OP catalog and program grouping without selecting a latest revision,
  merging `010` with `10`, or discarding duplicate sequences/source keys.
- Source values are not replaced with authoring defaults at this stage.

Default adapter limits: 128 MiB input, 16 MiB total reader output, 256 KiB per
protocol line, 100,000 rows across allowed tables, 60 seconds including input copy,
128 MiB Java heap and 64 MiB metaspace. These are separate limits: a 128 MiB Access
file is not guaranteed to fit the output budget. Decimals and integers beyond
JavaScript's safe integer range are returned as strings in catalog responses.

`AccessReader.available()` checks runtime presence only. It is not a production
readiness probe. Integrating routes still requires concurrency/session quotas,
owner tokens, streaming upload limits, readiness checks and resource isolation.
The Python adapter is blocking and must not run on the FastAPI event loop.

## Isolated Validation

From `ISO_api`:

```sh
docker build -f deploy/creator/Dockerfile.els-reader-test -t dt-els-reader-test:local .
docker run --rm --network none --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m --memory 512m --cpus 1 --pids-limit 128 dt-els-reader-test:local
```

The test image uses Python 3.10 and Java 17, does not start an API, does not mount
the running application's files, and does not contact Mongo or the platform.
`ELS_REQUIRE_RUNTIME=1` makes a missing Java/JAR runtime a failure instead of a skip.
The normal backend test suite skips only the actual-reader integration tests if
Java/JAR is absent; pure protocol/catalog tests still run.

The same image can test the checked-in fixtures by mounting
`test/creator/fixtures/els` read-only at `/fixtures`. The image's own generated
files and checked-in files should both pass before changing the supported formats.
Encrypted files, very large real-world Access databases and customer ELS data
have not been qualified. They must not be advertised as supported.

## Dependencies and Reader Choice

Pinned Maven dependencies: Jackcess 4.0.8, Commons Lang 3.18.0,
Commons Logging 1.3.5 and Gson 2.13.2. The POM fixes build-plugin versions as well.
JARs and Maven build output are not checked into Git. Jackcess's published parent
POM (`com.healthmarketscience:openhms-parent:2.0.7`) declares Apache License 2.0;
Commons Lang, Commons Logging and Gson also use Apache License 2.0. Verify notices
for the resolved transitive dependency set when packaging a release.

MDB Tools is present only in the test image for comparison. In MDB Tools 1.0.0,
`mdb-json` omits zero-length columns, making NULL and an empty string ambiguous.
Jackcess is used to preserve that distinction and obtain table/PK metadata.
This does not install Java or MDB Tools into the current production container.

Primary dependency references:

- https://jackcess.sourceforge.io/
- https://github.com/mdbtools/mdbtools/blob/v1.0.0/src/util/mdb-json.c
- https://commons.apache.org/proper/commons-lang/
- https://commons.apache.org/proper/commons-logging/
- https://github.com/google/gson

Before distributing the reader image or JAR, preserve third-party license/notice
files and the Java/Python/Debian image notices. The test image is not a hardened
production deployment and does not replace the production dependency review.

## Remaining Gates

Foundation verification on 2026-10-29: 35 tests passed against checked-in Access
files and again against freshly generated files in the isolated image. The normal
Python 3.10 creator suite passed 152 tests (9 actual-reader tests skipped there
because Java/JAR is not installed); those 9 ran in the isolated suite. Existing
frontend tests passed 54/54 and the TypeScript/Vite build passed. No production
container was replaced or restarted. Customer data and ELS-to-XML end-to-end
validation remain untested.

1. Strict ELS DTO/capability and mapping/default profiles; unchanged v1 compatibility.
2. Owned temporary sessions, upload/cancel/expiry API, OP selection and DT mapping.
3. Tool identity and ELS/NC validation policies, review-only XML roundtrip.
4. Operator UI, atomic apply/restore including Blobs, tools-only append.
5. Existing CAM/manual/NC and new ELS end-to-end regression coverage.

Do not expose an import button based solely on reader availability: project
mapping, evidence validation and safe application to an existing draft are not
implemented by this foundation.
