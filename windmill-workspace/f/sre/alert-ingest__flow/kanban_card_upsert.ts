// Hermes-T Kanban `ops` board write. Runs unconditionally, right after the
// raw ntfy notification (plan invariant #1: human sees it first) and before
// the deterministic runbook routing — so a kanban-write failure never blocks
// ntfy or routing (see continue_on_error on this module in flow.yaml).
//
// Idempotency: `alert:<alertname>:<instance>` is passed as
// `--idempotency-key` to `hermes kanban create`. hermes_cli/kanban_db.py's
// create_task() does the dedup itself — a non-archived task with a matching
// key short-circuits and returns its existing id instead of creating a
// duplicate — so re-firing the same alert updates nothing here; it's a
// pure lookup. This lines up with Alertmanager's `group_by: [alertname,
// instance]` (repeat_interval: 4h) in secret-alertmanager-config.secret.yaml
// — if grouping is ever widened, this key derivation must change with it or
// distinct instances will collapse onto one card.
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

async function hermesKanban(
  args: string[]
): Promise<{ stdout: string; stderr: string; code: number }> {
  const proc = Bun.spawn(
    [
      "kubectl",
      "-n",
      "hermes-t",
      "exec",
      "deploy/hermes-t",
      "--",
      "hermes",
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

export async function main(payload: any, matrix_chat_id: string) {
  const status: string = payload.status ?? "firing";
  const commonLabels: any = payload.commonLabels ?? {};
  const commonAnnotations: any = payload.commonAnnotations ?? {};
  const alerts: any[] = payload.alerts ?? [];
  const firstAlert = alerts[0] ?? {};
  const labels = firstAlert.labels ?? commonLabels;
  const annotations = firstAlert.annotations ?? commonAnnotations;

  const alertname: string = labels.alertname ?? "UnknownAlert";
  const instance: string = labels.instance ?? labels.namespace ?? "unknown";
  const severity: string = labels.severity ?? "warning";
  const summary: string = annotations.summary ?? alertname;
  const description: string = annotations.description ?? "";
  const startsAt: string = firstAlert.startsAt ?? "";
  const generatorURL: string = firstAlert.generatorURL ?? "";

  const idempotencyKey = `alert:${alertname}:${instance}`;
  const title = `${alertname} — ${instance}`;

  const bodyLines = ["source: alertmanager", `severity: ${severity}`, summary];
  if (description && description !== summary) bodyLines.push(description);
  if (startsAt) bodyLines.push(`startsAt: ${startsAt}`);
  if (generatorURL) bodyLines.push(`generator: ${generatorURL}`);
  if (alerts.length > 1) bodyLines.push(`(${alerts.length} alerts in group)`);

  // create is idempotent on idempotency_key — a repeat firing notification
  // for the same alertname+instance returns the existing card's id rather
  // than creating a second one.
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

  const completeResult = await hermesKanban([
    "complete",
    taskId,
    "--result",
    `Resolved via Alertmanager at ${new Date().toISOString()}`,
  ]);
  if (completeResult.code !== 0) {
    throw new Error(
      `hermes kanban complete failed (exit ${completeResult.code}): ${completeResult.stderr}`
    );
  }
  return { action: "completed", task_id: taskId, idempotency_key: idempotencyKey };
}
