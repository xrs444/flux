# Hermes-T Kanban — HomeProd workflow hub

hermes-agent ships a full Kanban subsystem, enabled here via `config-managed.yaml`
(`toolsets: [kanban]`, merged onto the PVC config by the `seed-config` initContainer —
see `deployment-hermes-t.yaml`). This doc records the conventions the rest of the
pipeline (Windmill, the triage cron job, OpenWolf hooks) assumes.

- UI: <https://hermes-t.xrs444.net/kanban>
- API: `/api/plugins/kanban/*` behind the Kanidm OIDC dashboard gate
- CLI: `kubectl -n hermes-t exec deploy/hermes-t -- /opt/hermes/.venv/bin/hermes kanban <cmd>`
  — **always the full `/opt/hermes/.venv/bin/hermes` path, never bare `hermes`.**
  `kubectl exec` (no shell) resolves PATH to `/opt/hermes/bin/hermes` first, a
  "docker exec privilege-drop shim" that switches to the `hermes` user, whose
  home dir (`/opt/data`) gets clamped to mode 700 (no group bits) sometime
  after pod boot — breaking the shim's own `.env` read. Reproducible, not
  fully diagnosed. Verified live 2026-09-16 — this exact bug failed every
  card in the first live security-backlog migration run.
- Statuses: `triage → todo → scheduled → ready → running → blocked → review → done → archived`
- **Safety property the pipeline leans on**: the dispatcher only claims a card
  when it is BOTH `status: ready` AND has an `assignee` set
  (`WHERE status = 'ready' AND assignee IS NOT NULL`, `kanban_db.py`) — `ready`
  alone is not sufficient. `hermes kanban create` without `--triage` lands
  directly in `ready` (verified live 2026-09-16, correcting an earlier wrong
  assumption in this doc that it landed in `todo`) — that's fine and inert as
  long as nothing sets an assignee, which nothing in this pipeline does.
  `--triage` parks a card in `triage` instead.
- **`triage` is NOT inert by default — `kanban.auto_decompose` must be
  `false` (bug-975, 2026-09-16).** hermes-agent's own `kanban.auto_decompose`
  defaults to **`true`**: a gateway dispatcher tick (interval 60s, up to
  `auto_decompose_per_tick: 3` per tick) that automatically flesh-outs,
  **assigns**, and **promotes to `ready`** any triage card, with zero human
  gate. hermes-agent's own source (`gateway/kanban_watchers.py`) has a
  comment acknowledging this exact failure mode: *"auto-decompose created
  and launched destructive tasks while the user [...]"*. Confirmed live: a
  migrated security-backlog card manually dragged into `triage` had its body
  auto-rewritten into a destructive action plan (`sudo loginctl
  terminate-user root` on a live host + a git push meant to trigger a
  fleet-wide CI/CD deploy) and a real worker was spawned within one
  dispatcher tick — killed within minutes; see `.wolf/buglog.json` bug-975.
  All three instances now set `kanban.auto_decompose: false` in
  `config-managed.yaml`. **`--triage` alone never provided the "inert"
  guarantee this doc previously claimed — disabling auto_decompose is what
  actually makes it true.** If you ever need auto-decompose's fan-out
  behavior for a deliberately-supervised workflow, re-enable it narrowly
  and watch the board closely; do not flip it back on globally.
- **`auto_decompose:false` closes ONE path, not the only one — the dashboard
  itself is a second, ungated path (bug-975 follow-up, 2026-09-19).**
  Dropping a card into the triage lane in the browser calls
  `POST /tasks/{id}/specify` directly from the frontend, independent of
  `auto_decompose` entirely — there's no server config that gates it, it's
  a hardcoded UX choice. Confirmed live: `auto_decompose:false` correctly
  stopped the background dispatcher tick (no second
  `kanban auto-decompose [...]` log line ever appeared), but a card
  manually dragged into triage still got auto-rewritten and auto-promoted
  a few minutes later via this separate path. Whether it also sets an
  assignee is an LLM judgment call each time — observed both ways across
  two cards — so "it usually doesn't assign" is not a safety boundary.
  **Given at least two independent paths can hand a card an assignee
  without a human choosing one, don't chase every path to `ready`+assigned
  — assume one will eventually succeed, and make sure nothing dangerous
  happens when it does.** See the `kanban-safe` profile below.
- **`kanban.default_assignee: kanban-safe` — the actual containment (bug-975
  follow-up, 2026-09-19).** `gateway/kanban_watchers.py`'s dispatcher reads
  this same config key to sweep up and dispatch any *existing* unassigned
  `ready` card, not just future ones — so before setting it, park anything
  currently `ready`+unassigned (`hermes kanban block <id> "..."`) or it gets
  swept immediately. `kanban-safe` is a dedicated profile (PVC-only state,
  see the bootstrap script below) whose `agent.disabled_toolsets` strips
  every dangerous built-in toolset (`terminal`, `code_execution`,
  `computer_use`, `delegation`, `cronjob`, `browser`, …), leaving only
  `kanban`, `memory`, and the three read-only observability MCPs
  (`mcp-loki`/`mcp-prometheus`/`mcp-kubernetes`). Verified against the
  *exact* function the dispatcher calls to build a worker's `--toolsets`
  pin (`hermes_cli.tools_config._get_platform_tools`) — **not** the
  `hermes tools list` display command, which does not reflect real
  restrictions and will show everything as enabled regardless. Two dead
  ends hit first: the top-level `toolsets:` key (used above for `kanban`)
  is purely *additive* — it adds a toolset on top of an always-on default
  set, confirmed live it restricts nothing — and `tools.allowed/denied` is
  already known dead (hermes-k's ConfigMap, verified 2026-07-21).
  `agent.disabled_toolsets` is the only key that actually works; it runs
  last and overrides everything else. Now that a card assigned this way
  can't do damage, an unblocked card auto-routes to `kanban-safe` and gets
  a (probably not very useful, since it can't touch infrastructure)
  read-only pass — real fixes still go through Claude Code, per the
  handoff section below.

## Boards

| Slug | Purpose | Bootstrapped by |
| --- | --- | --- |
| `ops` | Alerts, CI failures, incidents. Fast-moving, machine-created. | `bootstrap-boards.sh` |
| `projects` | User-entered work, upgrades, migrated security backlog. Held until actioned. | `bootstrap-boards.sh` |

Boards (and profiles) live on the PVC only, not in git — `bootstrap-boards.sh` is the
recovery path if the PVC is ever lost. Periodically run `hermes kanban boards export`
as part of the existing backup story.

**Board name resolution has no fuzzy/case-insensitive matching and fails by silently
creating a duplicate (bug-1005, 2026-09-22).** Asked to target "the HomeProd Projects
board" (display name of the real `projects` board), the model guessed a kebab-cased
slug and ran `hermes kanban boards create` instead of finding the existing board —
producing a duplicate (`homeprod-projects`, display name "Homeprod Projects") whose
cards then had to be reconciled by hand. Root cause, confirmed against hermes-agent's
own docs: the `kanban_create` agent tool has **no `board` parameter at all** and there
is **no `kanban_boards_list` (or any board-discovery) agent tool** — a model asked to
target a board by name has no way to resolve the real slug except shelling out via the
`terminal`/`code_execution` toolset (both enabled on the `default` profile, confirmed
live via `hermes tools list`) and guessing. `hermes kanban boards create` always
succeeds even when a matching board already exists under a different slug — no
case-insensitive match, no refuse-and-ask. hermes-agent is a prebuilt image here (no
`flux/apps/automation/hermes-t/custom-image/` — confirmed no vendored source), so this
isn't fixable in this repo's build, only mitigated by instruction: `/opt/data/
MEMORY.md` (the same always-active-memory pin mechanism already used for the CalDAV
collection-URL note below) now tells the model to always run `hermes kanban boards
list` (full `/opt/hermes/.venv/bin/hermes` path, via terminal) and resolve to the
exact existing **slug** before any board-create or board-targeted command — never a
typed/remembered display name. That pin is PVC-only and unversioned like the boards
themselves; re-add it from this note if the PVC is ever lost (see `/opt/data/
MEMORY.md`'s live content for the exact wording).

Separately investigated during the same incident: whether the CLI's "current board"
state (`~/.hermes/kanban/current`, selected via `hermes kanban boards switch <slug>`)
persists reliably across separate `kubectl exec` invocations, since one apparent
revert was observed live. Could not reproduce — repeated switch → list → new exec →
list cycles via the full hermes path all showed the switched board correctly. Left
unexplained rather than assigned a cause; worth another look only if it recurs.

## Card conventions

**`ops` cards** (alert/incident pipeline — see `flux/windmill-workspace/f/sre/alert-ingest__flow/`):

- Idempotency key (as of 2026-09-24, bug-1031): `alert:<alertname>:<k=v,k=v,...>`,
  derived from Alertmanager's `groupLabels` — the exact set named in `group_by`
  below, sorted, `instance` dropped when `job == "kube-state-metrics"` (that label
  is the KSM exporter's own pod IP there, not the alert's subject, and changes on
  every KSM restart). One card per distinct alert **group**, not per
  alertname+instance — the old key collapsed unrelated alerts sharing no
  `instance` label onto one card (9 distinct `TargetDown` jobs → one
  `TargetDown — unknown`) and re-split KSM alerts on every pod restart. See
  `kanban_card_upsert.ts`'s header comment for the full derivation.
- Created with `--triage` — always lands in `triage`, never dispatchable on arrival.
- `status: resolved` from Alertmanager **archives** the matching card (not
  `complete` — `kanban_db.complete_task()` only accepts a task already in
  `running/ready/blocked/review`; `triage` isn't in that set, so `hermes kanban
  complete` on an alert card fails every time with "unknown id or terminal
  state". This was the actual pipeline bug from 2026-09-16 (when the pipeline
  went live) to 2026-09-24 (found via a manual board triage pass, 63 cards stuck
  with zero ever closed) — invisible because the module runs with
  `continue_on_error: true`, so the parent flow job reported `success: true` on
  every run regardless. `archive_task()` has no source-status guard, so it works
  from `triage`; it also frees the idempotency key so the next firing of the same
  alert group gets a fresh lookup instead of silently matching a dead card. See
  bug-1031 in `.wolf/buglog.json`.)
- Note: Alertmanager's `group_by: [alertname, namespace, job, instance]`
  (`repeat_interval: 4h`) is what `groupLabels` reflects. If grouping is ever
  widened or narrowed again, the key derivation in `kanban_card_upsert.ts` must
  change with it.
- `Watchdog` and `InfoInhibitor` are never carded (they're dead-man's-switch /
  grouping-helper alerts, not faults) — filtered in `kanban_card_upsert.ts`
  before the create call.
- A belt-and-suspenders `ops-board-reconcile` `--no-agent` cron (hourly) archives
  any `triage` card whose alert has stopped firing in Alertmanager, independent
  of whether a `resolved` webhook ever arrived — added because Alertmanager
  losing its in-memory state (a pod restart) means it never sends one, which is
  exactly what happened 2026-09-21 and orphaned everything fired before it. See
  "Scheduled pulls" below.

**`projects` cards**:

- Created in `ready`, unassigned (not `triage` — no triage/enrichment sweep
  runs against this board).
- **This is NOT inert (bug-1006, 2026-09-22) — this doc's earlier claim that "the
  dispatcher requires an assignee too, and nothing sets one" is stale and wrong.**
  `kanban.default_assignee: kanban-safe` (set since bug-975's 2026-09-19 follow-up,
  see "Assignee" below) is board-agnostic: `gateway/kanban_watchers.py`'s dispatcher
  sweeps up *any* `ready`+unassigned card on *any* board, including `projects`, and
  dispatches it to `kanban-safe` within one tick (~60s). Confirmed live: 10 `projects`
  cards created the plain documented way (`hermes kanban create`, no `--assignee`) had
  8 swept to `running` before this was noticed. Confirmed via `hermes config get
  kanban` that the config schema is flat — `default_assignee` has no per-board
  override, so scoping the sweep to exclude `projects` isn't possible today. There is
  currently **no way to create a `projects` card that lands `ready`+unassigned and
  stays that way** — pick one:
  - `--triage` instead of the default (parks in `triage`, no sweep reads that status
    for `projects`-board cards — but see the `auto_decompose`/dashboard-drag warnings
    above if you ever touch it after creation), or
  - block immediately after creating: `hermes kanban block <id> --kind needs_input`
    (the workaround used live for today's 10 cards — safe since `kanban-safe` can't
    touch infrastructure, but still an unintended dispatch worth avoiding at the
    source).
- Moved to `scheduled` when parked on a future date, per `hermes kanban schedule`.

**All cards** — tag the source in the first line of the body:

```text
source: alertmanager | github | claude-code | user | cron
```

Used for provenance and to filter in the dashboard; not machine-enforced.

**`--board <slug>` is a top-level `kanban` flag and must come BEFORE the
subcommand** (`hermes kanban --board ops comment <id> ...`), not after it.
Every command below was fixed to this order 2026-09-24 (bug-1031) — the
previous form (`hermes kanban comment <id> --board ops`) fails outright with
`unrecognized arguments: --board ops`.

## Triage / enrichment sweep (read-only)

A `hermes cron` job sweeps `ops` board `triage` cards every 10 minutes. It's a
normal agent-mode cron job (not `--no-agent`), using only the four kanban
agent tools confirmed safe for this — `kanban_list`, `kanban_show`,
`kanban_comment`, `kanban_complete` — plus the read-only observability MCPs
already wired into hermes-t's config (`mcp-loki`, `mcp-prometheus`,
`mcp-kubernetes`, all `--read-only`/RBAC get-list-watch). It must never touch
`mcpjungle`'s read-write upstreams.

**Scoped down from the original plan, twice now:**

1. There is no `kanban_promote` (or any status-transition) agent tool —
   `promote`, like `notify-subscribe`, is CLI-only. A cron job's agent turn
   can't shell out to the CLI without a `terminal`/`code_exec` toolset that
   isn't confirmed enabled for cron profiles, so this sweep does **not** move
   cards `triage → todo`.
2. **`kanban_complete` cannot act on a `triage` card either** (bug-1031,
   2026-09-24) — `complete_task()`'s status guard only accepts
   `running/ready/blocked/review`, and there is no `kanban_archive` agent
   tool. The sweep's prompt originally told it to call `kanban_complete` on
   self-resolving/transient cards; that call was failing every time,
   silently, for the same reason the alert-ingest resolve path was (see
   "Card conventions" above). **As of 2026-09-24 the sweep is
   enrichment-comment only — it never attempts to close a card.** Closing
   happens via the alert-ingest resolve path (archives on `resolved`), the
   `ops-board-reconcile` cron (archives orphans hourly), or a human/Claude
   Code session acting on the sweep's own `claude` prompt block.

So: every triage card gets an enrichment comment (logs/metrics/blast-radius
correlated via the read-only MCPs, and whether it looks self-resolving) and,
if a fix looks needed, a `Claude Code` prompt block (see below). A bare
`triage` card = not yet swept; a `triage` card with a comment = enriched and
waiting on you (or on one of the two closing mechanisms above).

Installed live 2026-09-24 (job id `980ea8699475`):

```sh
kubectl -n hermes-t exec deploy/hermes-t -- /opt/hermes/.venv/bin/hermes cron create \
  --name ops-triage-sweep \
  "*/10 * * * *" \
  "Sweep the ops board's triage column. For each triage card: read it \
(kanban_show), then use mcp-loki/mcp-prometheus/mcp-kubernetes (read-only \
only — never mcpjungle's write-capable upstreams) to correlate logs, \
metrics, and recent cluster events for the affected host/namespace/service. \
Post an enrichment comment (kanban_comment) covering: what fired, \
correlated evidence, blast radius, and whether this looks self-resolving or \
already resolved. Do NOT attempt to change status, complete, or close any \
card — kanban_complete cannot act on a triage card (the underlying status \
guard only allows running/ready/blocked/review), and there is no archive \
tool available to you. Closing triage cards is handled by the alert-ingest \
resolve path and the ops-board-reconcile cron, not this sweep. If a \
code/config fix looks needed, append a \`\`\`claude fenced block to your \
comment with a ready-to-run prompt (card id, symptom, evidence already \
gathered, affected files/hosts, and an on-completion command run from the \
Mac: kubectl -n hermes-t exec deploy/hermes-t -- \
/opt/hermes/.venv/bin/hermes kanban --board ops comment <id> -m \
'<summary>' && kubectl -n hermes-t exec deploy/hermes-t -- \
/opt/hermes/.venv/bin/hermes kanban --board ops archive <id>). Never use \
kanban_list's or kanban_show's output to justify creating new cards, \
blocking, or any mutation beyond kanban_comment."
```

## Claude Code handoff (prompt-only)

Cards needing a code/config change carry a fenced, copy-pasteable block in
their enrichment comment:

````text
```claude
cd ~/Repositories/HomeProd && claude
```
Prompt:
Card ops/<task_id> — <title>
Symptom: …
Evidence: <loki/prom queries already run, with results>
Affected: <hosts, files, namespaces>
Scope: <what to change; what not to touch>
On completion (run from the Mac, not bare hermes) — archive, not complete;
see "Card conventions" above for why:
  kubectl -n hermes-t exec deploy/hermes-t -- /opt/hermes/.venv/bin/hermes \
    kanban --board ops comment <task_id> -m "<summary>" && \
  kubectl -n hermes-t exec deploy/hermes-t -- /opt/hermes/.venv/bin/hermes \
    kanban --board ops archive <task_id>
````

The card waits in `triage` until you act — nothing here starts a Claude Code
session automatically. You read the board at
<https://hermes-t.xrs444.net/kanban>, paste the prompt into a session
started in the repo, and the session posts its own comment + completion when
done (see "Feedback from Claude Code" below).

A Mac-side auto-launcher (a launchd agent on xlt1-t polling
`/api/plugins/kanban/board` and running `claude -p` for explicitly flagged
cards) fits here later without reworking anything — the card format is the
interface. The hermes-t pod itself is not a candidate: it has `node`/`npm`/
`git` but no `claude`, no repo checkout, no kubectl, and no Anthropic
credentials.

## Feedback from Claude Code

`.wolf/hooks/kanban-sync.js` (`SessionEnd`) and the `/card` skill close the
loop — see `.claude/skills/card.md` in this repo. A session started from a
card's prompt block runs `/card start <id>`, and on session end the hook
posts a wrap-up comment via `kubectl exec` — it deliberately never completes
or archives the card itself (a session that crashes or hits a context limit
shouldn't get its card marked done just because the session ended); only an
explicit `/card done` does that. `/card done` archives `ops`-board cards
(they live in `triage`, which `complete` can't act on — see Card conventions
above) and completes `projects`-board cards (created in `ready`, where
`complete` works normally). Neither path touches `.wolf/buglog.json` — that
file stays the post-fix forensic archive it always was, unrelated to board
state.

## Migrating the security backlog

`migrate-security-backlog.py` is a one-time script, not a Flux resource —
same category as `bootstrap-boards.sh`. It parses `.wolf/security-backlog.md`
(reusing the exact classification heuristic from
`.claude/skills/security-backlog-triage.md`: title contains
RESOLVED/DONE → skip, DEFERRED → open-but-lower-urgency, no suffix → open;
the "DONE (reference)" and "LOW / INFO / REPORT-ONLY" sections are excluded
entirely per their own headings) and creates one `projects` card per open
item, preserving the file's `C*`/`H*`/`M*`/`BUG-*`/`V*`/`F*`/`N*`/`T*` id
prefixes in the title and copying the item's full body verbatim.

**Dry-run by default** — verified against the live file (2026-09-15): 24
total items, 16 open. Review the dry-run output before applying; this
writes real, hard-to-cleanly-bulk-delete cards onto a board nobody has used
yet.

```sh
python3 flux/apps/automation/hermes-t/migrate-security-backlog.py            # dry run
python3 flux/apps/automation/hermes-t/migrate-security-backlog.py --apply    # create cards
```

Safe to re-run: every card carries `--idempotency-key security-backlog:<ID>`,
so a second run after a partial failure creates nothing twice. After
migrating, treat `security-backlog.md` as a historical document — the board
is the tracker going forward.

## Scheduled pulls

**All jobs below were documented but never actually installed until
2026-09-24 (bug-1031) — `hermes cron list` returned "No scheduled jobs" the
entire time, which is why every card on the board was bare with no
enrichment comment.** Now live: `ops-triage-sweep` (`980ea8699475`),
`gh-actions-watch` (`8c74d34dc21f`), `infra-health-rollup` (`8b53689bed00`),
`ops-board-reconcile` (`4db328b0dffa`). `hermes cron list` reflects current
state; job ids here are a point-in-time reference, not load-bearing.

**GitHub Actions failures** (`flux/`'s workflows notify nobody today, unlike
`nix/`'s Apprise-wired ones — see `scripts/gh-actions-watch.sh`). One-time
install onto the PVC (cron jobs and their scripts live there, same as
boards/profiles — not Flux-managed):

```sh
kubectl -n hermes-t cp flux/apps/automation/hermes-t/scripts/gh-actions-watch.sh \
  hermes-t/$(kubectl -n hermes-t get pod -l app=hermes-t -o jsonpath='{.items[0].metadata.name}'):/opt/data/scripts/gh-actions-watch.sh

kubectl -n hermes-t exec deploy/hermes-t -- /opt/hermes/.venv/bin/hermes cron create \
  --name gh-actions-watch \
  --monitor-script gh-actions-watch.sh \
  "*/30 * * * *" \
  "GitHub Actions failures changed for xrs444/nix or xrs444/flux (see the \
MONITOR CHANGE DETECTED diff above). Create or update an ops-board card \
per distinct failing workflow run, idempotency key \
github:<repo>:<workflow>:<run_number>, --triage."
```

If either repo is private, unauthenticated GitHub API calls will 401 —
export `GITHUB_TOKEN` in a copy of the script on the PVC (`--monitor-script`
has no per-job env var option). Unauthenticated calls are fine for public
repos at this poll interval (4 calls/30min, well under the 60/hr limit).

**Daily infra-health rollup**: uses the `homeprod:*:state` recording rules in
`flux/apps/observability/monitoring/prometheusrule-status-state.yaml`
(`homeprod:host:state`, `homeprod:talos_node:state`, `homeprod:net:state`,
`homeprod:endpoint:state`, `homeprod:storage:state`, `homeprod:infra:state`,
`homeprod:app:state`; 0=GOOD/1=CAUTION/2=WARNING) via the already-wired
`mcp-prometheus` read-only MCP. Agent-mode cron (not `--no-agent` — judging
"is this worth a card" needs the LLM), using the native `kanban_create`
tool directly (no kubectl-exec needed here, unlike the Windmill flows —
this runs as an agent turn inside hermes-t itself).

**`kanban_create`'s JSON schema requires `assignee`** (`required: ["title",
"assignee"]` in `KANBAN_CREATE_SCHEMA`, `tools/kanban_tools.py`) — unlike
the CLI, where `--assignee` is optional. This is harmless for a `triage`
card (assignee doesn't affect dispatch; only `status: ready` does), but the
prompt below must always pass one (`default`, the only profile that
exists) or every creation call fails validation.

```sh
kubectl -n hermes-t exec deploy/hermes-t -- /opt/hermes/.venv/bin/hermes cron create \
  --name infra-health-rollup \
  "0 8 * * *" \
  "Query mcp-prometheus for homeprod:host:state, homeprod:talos_node:state, \
homeprod:net:state, homeprod:endpoint:state, homeprod:storage:state, \
homeprod:infra:state, homeprod:app:state. For each series with value >= 1 \
(CAUTION or WARNING), use kanban_create (title, assignee: 'default', \
triage: true, idempotency_key: infra-health:<metric>:<labels>, board: ops) \
to create or upsert a card summarizing which host/node/service and at what \
severity. If everything is 0 (GOOD), create nothing — do not post a daily \
all-clear card."
```

**Ops-board reconciler** (`ops-board-reconcile`, added 2026-09-24, bug-1031
follow-up): a `--no-agent` cron, hourly, at
`flux/apps/automation/hermes-t/scripts/ops-board-reconcile.py` — installed
onto the PVC the same way as `gh-actions-watch.sh` above (`kubectl cp` to
`/opt/data/scripts/`). It exists because the resolve path (archiving on a
`resolved` webhook) only works if Alertmanager actually sends one — and it
won't if Alertmanager loses its in-memory state (a pod restart, e.g. the one
on 2026-09-21T20:17Z that orphaned every card fired before it). The script
queries Alertmanager's `/api/v2/alerts/groups` directly (not via
mcp-prometheus — this is `--no-agent`, no agent tool access), rebuilds each
`triage` card's idempotency key from its title using the identical derivation
`kanban_card_upsert.ts` uses to create it, and archives any card whose key
matches no currently-active group.

Requires a `CiliumNetworkPolicy` egress rule from `hermes-t` to
`monitoring`/`alertmanager:9093` — added to
`ciliumnetworkpolicy-hermes-t.yaml` in the same change (`monitoring` isn't
itself T1-onboarded yet, so only hermes-t's own egress needed the allow).
**This cron will fail every run until that CNP change is deployed
(commit+push, Flux reconciles it)** — check `hermes cron runs
ops-board-reconcile` for a connection-refused/timeout error as the signal
it's not live yet.

**Alert-ingest pipeline self-check** (`f/sre/alert-ingest-health`, added
2026-09-24, bug-1031 follow-up): a Windmill schedule, hourly, NOT a `hermes
cron` — lives in `flux/windmill-workspace/f/sre/`, deployed via `wmill sync
push` like the rest of that workspace. Exists for the same reason the bug
above went undetected for 8 days: `kanban_card_upsert`'s `continue_on_error:
true` means the parent flow job reports `success: true` even when that step
throws on every single run. There is no Prometheus metric to alert on this
(confirmed live — zero `windmill_*` series scraped; `up{job="windmill"}` only
covers worker liveness, not per-script outcomes), so this queries Windmill's
own job-history API directly for recent `kanban_card_upsert` failures on
either `f/sre/alert-ingest` or `f/sre/flux-alert-ingest`, and pings ntfy's
`alerts-warning` topic if it finds any. A last-resort watchdog for the thing
that watches everything else — nothing else watches it.

## Assignee

Deliberate, human-driven work (the triage sweep's comments, Claude Code sessions)
routes through the `default` profile, same as before. As of bug-975 (2026-09-19),
a second profile — `kanban-safe` — exists specifically as `kanban.default_assignee`:
the fallback anything auto-assigned via a path a human didn't choose lands on. See
the safety-property notes above for why, and `bootstrap-kanban-safe-profile.sh` (same
disaster-recovery category as `bootstrap-boards.sh` — profile state is PVC-only and
unversioned) to recreate it if the PVC is ever lost.
