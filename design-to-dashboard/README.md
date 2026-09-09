# Design-to-Dashboard

Turns a Figma export or dashboard screenshot + a natural-language requirement into a working Superset dashboard in the CloudKeeper Analytics fork.

## Documents

| File | What it is |
|---|---|
| `BUILD_SPEC.md` | Engineering brief — architecture, endpoints, security, delivery order |
| `PIPELINE_CONTRACT.md` | Stage I/O schemas, shared types, orchestration rules |
| `prompts/shared/_preamble.md` | Identity + hard constraints, prepended to every stage |
| `prompts/A_decompose_design.md` … `F_scaffold_plugin.md` | One prompt per pipeline stage |
| `EXAMPLE_RUN.md` | Full worked trace of one design through all six stages; doubles as test fixtures |
| `MCP_INTEGRATION.md` | What Superset 6.1's MCP server gives us, what it can't, and the hybrid architecture |
| `PLUGIN_DEPLOYMENT.md` | What it takes to make a generated plugin usable — static rebuild vs. dynamic loading |
| `UI_PLAN.md` | Where the UI lives in Superset, how it's wired, and the six-state interaction model |

## Run traces

Every run writes its own trace when it ends -- succeeded, failed or cancelled:

```
design-to-dashboard/traces/<session-id>.md
```

Per stage: duration, cost, the reasoning, the tool calls, the decisions and the
thumbnail evidence behind them, plus both human gates and what finally
rendered. This is the artifact for judging how well the model performed.

The directory is git-ignored, so traces are local to your machine and your
editor may hide them. Sessions live in the web process's memory, so a trace is
the *only* thing that survives a restart -- which is why the runner writes it
rather than leaving it to be exported by hand.

To re-export a session that is still in memory (to pick up events published
after its trace was written, or to write it elsewhere):

```bash
python design-to-dashboard/scripts/export_trace.py <session-id> [--out FILE]
```

## Why six stages and not one agent

The viz registry is ~567 KB of control-panel source across 72 registered `viz_type`s (~140k tokens raw). Any single chart needs exactly one entry from it (~3k tokens). A single agent carrying the whole registry is both expensive and worse at choosing, so the pipeline splits **by what context each step needs**, not by task verb:

```
  A decompose ──> B bind ──> C resolve ──┬─> D configure (×N, parallel) ──┐
   (vision)      (datasets)   (the brain)│                                ├─> apply
                                         ├─> F scaffold  (×K, rare)  ─────┤
                                         └─> E layout    (geometry)  ─────┘
```

- The design image lives only in **A** and never reappears downstream.
- **B** and **C** are agentic — they discover datasets and reusable charts through MCP tools instead of carrying a dumped catalogue.
- **C** sees viz-type *summaries* (name, category, tags) — enough to choose, not to configure.
- **D** sees exactly one control schema per invocation — the 45× context win.
- **C** stays a single wide-context call on purpose: global decisions need a global view.

This is a **pipeline with one fan-out**, orchestrated by deterministic Python — not agents negotiating. That buys per-stage retries, schema validation, caching, and unit-testable boundaries.
