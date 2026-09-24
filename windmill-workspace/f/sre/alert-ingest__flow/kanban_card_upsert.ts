// Hermes-T Kanban `ops` board write. Runs unconditionally, right after the
// raw ntfy notification (plan invariant #1: human sees it first) and before
// the deterministic runbook routing — so a kanban-write failure never blocks
// ntfy or routing (see continue_on_error on this module in flow.yaml).
//
// Idempotency: the key is derived from Alertmanager's `groupLabels` — the
// exact label set named in `group_by` in secret-alertmanager-config.secret.yaml
// — sorted `k=v` pairs joined with commas, e.g. `alertname=TargetDown,job=snmp`.
// `groupLabels` is identical between a group's firing and resolved
// notifications, so the resolve is guaranteed to match its firing card by
// construction. Using `alerts[0].labels` instead (the old approach) was
// wrong in both directions: labels absent from the group key (e.g.
// `TargetDown` carries no `instance`) collapsed distinct alerts onto one
// card, while labels that vary run-to-run but aren't part of the group
// (kube-state-metrics alerts keyed on the KSM pod's own IP) re-carded the
// same condition on every KSM restart. See KANBAN.md's Card conventions
// section — the two must change together if `group_by` is ever widened.
//
// `--idempotency-key` is passed to `hermes kanban create`.
// hermes_cli/kanban_db.py's create_task() does the dedup itself — a
// non-archived task with a matching key short-circuits and returns its
// existing id instead of creating a duplicate — so re-firing the same
// alert group updates nothing here; it's a pure lookup.
//
// Transport is `kubectl exec` into the hermes-t pod rather than hitting its
// dashboard REST API directly: the `default` worker group already carries
// the windmill-runner ServiceAccount for in-cluster kubectl (used today by
// the ansible-language lab/rack power scripts), and exec traffic goes via
// the k8s API server so no CiliumNetworkPolicy change is needed. Requires
// the windmill-runner Role/RoleBinding granting `pods/exec` create in the
// hermes-t namespace (see flux/apps/automation/hermes-t/rbac-windmill-runner-exec.yaml).
//
// Cards always land in `triage` (`--triage`) — never `--initial-status
// ready` — so nothing created here can be claimed and dispatched as a
// worker. Only an explicit human/cron `hermes kanban promote` moves a card
// out of triage/todo.

// Windmill's Bun.spawn() does not pass the worker pod's environment
// through to spawned children — KUBERNETES_SERVICE_HOST/PORT are absent,
// so kubectl's in-cluster auto-detection falls back to its ancient
// localhost:8080 default and fails with "connection refused". Confirmed
// live 2026-09-16 (reproduced the identical error by stripping those vars
// manually; kubectl works fine with them present). Explicit --server/
// --token/--certificate-authority flags, reading the projected service
// account files directly, don't depend on env vars at all.
const K8S_SERVER = "https://kubernetes.default.svc:443";
const K8S_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token";
const K8S_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt";

async function hermesKanban(
  args: string[]
): Promise<{ stdout: string; stderr: string; code: number }> {
  const token = (await Bun.file(K8S_TOKEN_PATH).text()).trim();
  const proc = Bun.spawn(
    [
      "kubectl",
      "--server",
      K8S_SERVER,
      "--token",
      token,
      "--certificate-authority",
      K8S_CA_PATH,
      "-n",
      "hermes-t",
      "exec",
      "deploy/hermes-t",
      "--",
      // Full path, not bare "hermes" — kubectl exec (no shell) resolves PATH
      // to /opt/hermes/bin/hermes FIRST, a "docker exec privilege-drop shim"
      // that switches to the hermes user before running the real CLI. That
      // user's own home dir (/opt/data) gets clamped to mode 700 (no group
      // bits) sometime after pod boot — cause not fully diagnosed, but
      // reproducible — so the shim intermittently can't even read its own
      // .env. The .venv path bypasses the shim entirely and runs as
      // whatever identity invoked kubectl exec (root, in this transport),
      // which isn't subject to that restriction. Verified live 2026-09-16.
      "/opt/hermes/.venv/bin/hermes",
      "kanban",
      "--board",
      "ops",
      ...args,
    ],
    { stdout: "pipe", stderr: "pipe" }
  );
  const [stdout, stderr] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
  ]);
  const code = await proc.exited;
  return { stdout, stderr, code };
}

// Alertmanager fires this permanently by design (dead-man's-switch) or as a
// grouping helper, not a fault — never worth a card. Checked against
// groupLabels.alertname so it's caught regardless of which alert in the
// group happens to be alerts[0].
const NEVER_CARD_ALERTNAMES = new Set(["Watchdog", "InfoInhibitor"]);

export async function main(payload: any, matrix_chat_id: string) {
  const status: string = payload.status ?? "firing";
  const groupLabels: any = payload.groupLabels ?? {};
  const commonLabels: any = payload.commonLabels ?? {};
  const commonAnnotations: any = payload.commonAnnotations ?? {};
  const alerts: any[] = payload.alerts ?? [];
  const firstAlert = alerts[0] ?? {};
  const labels = firstAlert.labels ?? commonLabels;
  const annotations = firstAlert.annotations ?? commonAnnotations;

  const alertname: string = groupLabels.alertname ?? labels.alertname ?? "UnknownAlert";
  if (NEVER_CARD_ALERTNAMES.has(alertname)) {
    return { action: "skipped", reason: `${alertname} is never carded` };
  }

  const severity: string = labels.severity ?? "warning";
  const summary: string = annotations.summary ?? alertname;
  const description: string = annotations.description ?? "";
  const startsAt: string = firstAlert.startsAt ?? "";
  const generatorURL: string = firstAlert.generatorURL ?? "";

  // Idempotency key + title from groupLabels (see comment block above) —
  // falls back to commonLabels/labels only if Alertmanager ever omits
  // groupLabels (shouldn't happen for a webhook receiver, but cheap to guard).
  const keySource = Object.keys(groupLabels).length > 0 ? groupLabels : labels;
  // kube-state-metrics alerts' `instance` is the KSM exporter pod's own
  // address, not the alert's subject — it changes on every KSM restart
  // (confirmed live: the same condition re-carded under 3 different pod
  // IPs). namespace + alertname already identify the condition without it.
  const isKsmAlert = keySource.job === "kube-state-metrics";
  const keyParts = Object.entries(keySource)
    .filter(([k]) => k !== "alertname" && !(isKsmAlert && k === "instance"))
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`);
  const idempotencyKey = `alert:${alertname}${keyParts.length ? ":" + keyParts.join(",") : ""}`;
  const title = keyParts.length ? `${alertname} — ${keyParts.join(", ")}` : alertname;

  const bodyLines = ["source: alertmanager", `severity: ${severity}`, summary];
  if (description && description !== summary) bodyLines.push(description);
  if (startsAt) bodyLines.push(`startsAt: ${startsAt}`);
  if (generatorURL) bodyLines.push(`generator: ${generatorURL}`);
  if (alerts.length > 1) bodyLines.push(`(${alerts.length} alerts in group)`);

  // create is idempotent on idempotency_key — a repeat firing notification
  // for the same alert group returns the existing card's id rather than
  // creating a second one.
  const createResult = await hermesKanban([
    "create",
    title,
    "--body",
    bodyLines.join("\n"),
    "--triage",
    "--idempotency-key",
    idempotencyKey,
    "--created-by",
    "alertmanager",
    "--json",
  ]);
  if (createResult.code !== 0) {
    throw new Error(
      `hermes kanban create failed (exit ${createResult.code}): ${createResult.stderr}`
    );
  }
  const task = JSON.parse(createResult.stdout);
  const taskId: string = task.id;

  // Idempotent on (task, platform, chat, thread) — safe to call on every
  // upsert, not just first creation. So the Matrix home channel gets a
  // notification the moment a triage-sweep or manual action changes the
  // card's terminal state, without polling the dashboard.
  if (matrix_chat_id) {
    const subResult = await hermesKanban([
      "notify-subscribe",
      taskId,
      "--platform",
      "matrix",
      "--chat-id",
      matrix_chat_id,
      "--delivery-mode",
      "notify",
    ]);
    if (subResult.code !== 0) {
      console.error(`notify-subscribe failed (non-fatal): ${subResult.stderr}`);
    }
  }

  if (status !== "resolved") {
    return { action: "upserted", task_id: taskId, idempotency_key: idempotencyKey };
  }

  // Close by archiving, not completing. kanban_db.complete_task() only
  // accepts a card already in running/ready/blocked/review — never triage,
  // which is where every alert card lands and stays (see the module comment
  // above). `hermes kanban complete` on a triage card fails every time with
  // "unknown id or terminal state" (confirmed live — this was the pipeline's
  // actual bug: every resolve since 2026-09-16 threw here, masked by
  // continue_on_error on this module in flow.yaml). archive_task()'s guard
  // is `status != 'archived'` — no source-status restriction, so it works
  // unconditionally. It's also strictly safer than "promote then complete":
  // promoting to ready+unassigned would sit in kanban.default_assignee's
  // sweep path and get dispatched to the kanban-safe profile within ~60s
  // (see KANBAN.md) — a real dispatch on every routine alert resolution.
  // Archiving also frees the idempotency key, so create_task()'s dedup
  // (which only matches non-archived tasks) won't silently swallow the next
  // time this same alert group fires.
  const commentResult = await hermesKanban([
    "comment",
    taskId,
    `Resolved via Alertmanager at ${new Date().toISOString()}`,
  ]);
  if (commentResult.code !== 0) {
    console.error(`kanban comment failed (non-fatal): ${commentResult.stderr}`);
  }
  const archiveResult = await hermesKanban(["archive", taskId]);
  if (archiveResult.code !== 0) {
    throw new Error(
      `hermes kanban archive failed (exit ${archiveResult.code}): ${archiveResult.stderr}`
    );
  }
  return { action: "archived", task_id: taskId, idempotency_key: idempotencyKey };
}
