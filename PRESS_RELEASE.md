# PRESS RELEASE

## MCP Tool Shop Announces nexus-router: Event-Sourced Routing for Auditable AI Tool Orchestration

**January 27, 2025** — MCP Tool Shop today released **nexus-router v0.1.1**, an open-source event-sourced router for Model Context Protocol (MCP) tool orchestration. The project addresses a critical gap in AI agent infrastructure: the need for complete auditability and policy enforcement when AI systems execute multi-step tool plans.

### The Problem

As AI agents become more capable, they're executing increasingly complex tool chains — reading files, querying databases, calling APIs, modifying code. But most orchestration layers treat these operations as fire-and-forget: you get a result, maybe a log line, and hope nothing went wrong.

This creates real problems:
- **No audit trail** — When something breaks, you can't replay what happened
- **No policy enforcement** — Agents can exceed their authorized scope
- **No integrity verification** — You can't prove what was executed

### The Solution

nexus-router applies event sourcing — a pattern proven in financial systems and distributed databases — to AI tool orchestration. Every operation is captured as an immutable event with cryptographic provenance:

```
RUN_STARTED → PLAN_CREATED → STEP_STARTED → TOOL_CALL_REQUESTED →
TOOL_CALL_SUCCEEDED → STEP_COMPLETED → PROVENANCE_EMITTED → RUN_COMPLETED
```

Each run produces a SHA256-signed provenance bundle that can be verified, replayed, and audited.

### Key Capabilities

- **Policy Gating**: `allow_apply` prevents destructive operations; `max_steps` enforces execution limits
- **Schema Validation**: Requests are validated against JSON Schema before execution
- **Fail-Early Design**: Policy violations trigger immediate `RUN_FAILED` events, not silent truncation
- **Exception Transparency**: Unexpected errors are recorded to the event log, then re-raised — bugs surface loudly

### Technical Details

- **Storage**: SQLite with WAL mode, supports both ephemeral (`:memory:`) and persistent databases
- **Sequencing**: Monotonic event sequences with unique index enforcement
- **Hashing**: Canonical JSON serialization for deterministic SHA256 digests
- **Versioning**: Immutable method IDs (`nexus-router.run_v0_1`) — new behavior means new ID

### What's Next

v0.1.1 is the foundation. The roadmap includes:
- **v0.2**: Real tool dispatch (currently fixture-driven with `plan_override`)
- **v0.3**: Tool registry integration and parallel step execution
- **v1.0**: Production hardening, concurrent writer support, streaming events

### Availability

nexus-router is available now under the MIT license:

- **GitHub**: https://github.com/mcp-tool-shop/nexus-router
- **Install**: `pip install git+https://github.com/mcp-tool-shop/nexus-router.git`

### About MCP Tool Shop

MCP Tool Shop builds infrastructure for AI agent orchestration, with a focus on auditability, safety, and developer experience.

---

**Contact**: tools@mcp-tool-shop.dev
**Repository**: https://github.com/mcp-tool-shop/nexus-router
**Release**: v0.1.1
