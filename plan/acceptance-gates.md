
# Pocket-Dock Milestone Acceptance Lists

Each milestone is **accepted only if all items pass**.

---

## **M0 — Podman Socket Connectivity & Exec Lifecycle**

**Goal:** Prove reliable, programmatic control of containers via Unix socket.

### Acceptance

* [ ] SDK can connect to Podman via Unix socket (rootless)
* [ ] Can list containers and images
* [ ] Can create a container (paused or stopped)
* [ ] Can start and stop a container
* [ ] Can create an exec inside a running container
* [ ] Exec lifecycle states are observable (created → running → exited)
* [ ] All operations fail cleanly if socket is unavailable
* [ ] No global state; all connections are per operation
* [ ] No CLI yet — SDK only

**Hard No**

* ❌ No streaming yet
* ❌ No sessions
* ❌ No project state

---

## **M1 — Streaming Exec Output (Stdout/Stderr)**

**Goal:** Reliable, non-blocking streaming without deadlocks.

### Acceptance

* [ ] `run()` can stream stdout in real time
* [ ] stderr is captured independently from stdout
* [ ] Output can be:

  * buffered
  * streamed
  * logged
    simultaneously
* [ ] Streaming does not block process completion
* [ ] Large outputs (>10MB) do not deadlock
* [ ] Stream ends correctly on exec exit
* [ ] Broken socket mid-stream raises deterministic error
* [ ] Output ordering is preserved per stream

**Hard No**

* ❌ No stdin
* ❌ No interactivity
* ❌ No sessions

---

## **M2 — Container Creation & Image Resolution**

**Goal:** Deterministic container creation and image handling.

### Acceptance

* [ ] Can pull images if missing
* [ ] Can run against locally available images
* [ ] Image resolution logic is deterministic
* [ ] Container names are predictable and collision-safe
* [ ] Containers are labeled with pocket-dock metadata
* [ ] Temporary containers are cleaned up on success
* [ ] Cleanup occurs on failure paths
* [ ] SDK user can opt into reuse vs ephemeral containers

---

## **M3 — Project-Scoped State & Instance Registry**

**Goal:** Make container state understandable and local.

### Acceptance

* [ ] `.project/.pocket-dock/instances/` is created automatically
* [ ] Each instance has:

  * ID
  * image
  * command history
  * timestamps
* [ ] Instance metadata survives process restarts
* [ ] State reflects actual container status on reconnect
* [ ] Orphaned containers are detected and flagged
* [ ] Deleting project state does not break system stability

---

## **M4 — Deterministic Error Model**

**Goal:** Fail loudly, consistently, and usefully.

### Acceptance

* [ ] All errors are typed (no raw exceptions)
* [ ] Errors include:

  * category
  * operation
  * container/exec ID (if applicable)
* [ ] Network/socket failures are distinguishable from runtime failures
* [ ] Container-not-found vs exec-not-found are distinct
* [ ] Timeouts are explicit, not implicit
* [ ] Errors are stable across identical failure conditions

---

## **M5 — Sessions (Interactive Shells)**

**Goal:** Human-oriented interactive workflows.

### Acceptance

* [ ] `session.start()` opens a shell inside container
* [ ] Input can be written incrementally
* [ ] Output streams continuously
* [ ] Sentinel or control protocol reliably detects prompt return
* [ ] Session can be closed cleanly
* [ ] Session cleanup occurs on process crash
* [ ] Session behavior is documented as “best-effort”
* [ ] Session failure does not corrupt container state

**Explicit Limitation**

* Sessions are not guaranteed for:

  * full-screen TUIs
  * non-cooperative binaries

---

## **M6 — Embedded Profile (Base Toolchain Image)**

**Goal:** Offline-ready, reproducible baseline.

### Acceptance

* [ ] Embedded image builds reproducibly
* [ ] Image can be exported/imported without network
* [ ] Includes documented base toolchain only
* [ ] Image version is pinned and inspectable
* [ ] SDK can verify image presence
* [ ] Users can override image cleanly
* [ ] No runtime image mutation

---

## **M7 — Snapshots & Custom Images**

**Goal:** Controlled extensibility without SDK complexity.

### Acceptance

* [ ] Snapshot creates new image from running container
* [ ] Snapshot metadata is recorded
* [ ] Snapshots are nameable and reusable
* [ ] SDK can run against snapshot images
* [ ] Custom Dockerfile/Containerfile flow documented
* [ ] Snapshot failures do not affect original container

---

## **M8 — CLI (Power User Surface)**

**Goal:** Thin, honest CLI over SDK.

### Acceptance

* [ ] CLI maps 1:1 to SDK calls
* [ ] No CLI-only behavior
* [ ] CLI shows streaming output correctly
* [ ] Errors are readable and mapped from SDK errors
* [ ] CLI state matches project state
* [ ] `--verbose` exposes raw operation details
* [ ] CLI does not introduce new persistence

---

## **M9 — Documentation & Examples**

**Goal:** Make it usable without hand-holding.

### Acceptance

* [ ] README explains mental model in <10 minutes
* [ ] Quickstart works offline
* [ ] One SDK example per major feature
* [ ] Session limitations are clearly documented
* [ ] Failure modes are explained
* [ ] Image/snapshot model is explained visually or stepwise

---

## **M10 — Hardening & Release Gate**

**Goal:** Decide if this is 1.0-worthy.

### Acceptance

* [ ] All milestones M0–M9 pass
* [ ] No known deadlocks under stress tests
* [ ] No resource leaks (containers, execs, sockets)
* [ ] Works across Podman minor versions
* [ ] Docker compatibility assessed (even if partial)
* [ ] Versioning and backward-compatibility policy written
* [ ] Explicit non-goals documented
