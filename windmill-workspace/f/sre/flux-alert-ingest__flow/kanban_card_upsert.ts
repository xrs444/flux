// Same `hermes kanban` CLI / kubectl-exec transport as
// f/sre/alert-ingest__flow/kanban_card_upsert.ts — see that file's header
// comment for the full rationale (idempotency dedup, --triage safety,
// RBAC). This one reads Flux's Event shape instead of Alertmanager's.
//
// Idempotency key is `flux:<kind>:<namespace>/<name>` — one card per
// distinct Flux object, re-firing (Flux retries every `interval`, e.g. 10m,
// until the object recovers) updates the existing card instead of
// duplicating it. There is no synthesized "resolved" transition here: Flux's
// event stream doesn't carry a reliable per-object "this specific failure
// is now fixed" signal the way Alertmanager's `status: resolved` does, and
// eventSeverity: error on the Alert CR means we only ever see failures, not
// recoveries. These cards are expected to be completed by a human/Claude
// Code once fixed, or by Phase 3's read-only triage sweep re-checking the
// object's health via mcp-kubernetes.

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
  const involved = payload.involvedObject ?? {};
  const kind: string = involved.kind ?? "Resource";
  const name: string = involved.name ?? "unknown";
  const namespace: string = involved.namespace ?? "flux-system";
  const reason: string = payload.reason ?? "ReconciliationFailed";
  const message: string = payload.message ?? "";
  const timestamp: string = payload.timestamp ?? "";

  // Defensive re-check even though the Alert CR's eventSeverity: error
  // should mean Flux never sends anything else to this webhook.
  const severity: string = payload.severity ?? "error";
  if (severity !== "error") {
    return { action: "skipped", reason: `severity=${severity}, not error` };
  }

  const idempotencyKey = `flux:${kind}:${namespace}/${name}`;
  const title = `Flux ${kind}/${name} — ${reason}`;

  const bodyLines = [
    "source: flux",
    `namespace: ${namespace}`,
    `reason: ${reason}`,
    message,
  ].filter(Boolean);
  if (timestamp) bodyLines.push(`timestamp: ${timestamp}`);

  const createResult = await hermesKanban([
    "create",
    title,
    "--body",
    bodyLines.join("\n"),
    "--triage",
    "--idempotency-key",
    idempotencyKey,
    "--created-by",
    "flux",
    "--json",
  ]);
  if (createResult.code !== 0) {
    throw new Error(
      `hermes kanban create failed (exit ${createResult.code}): ${createResult.stderr}`
    );
  }
  const task = JSON.parse(createResult.stdout);
  const taskId: string = task.id;

  // Idempotent on (task, platform, chat, thread) — safe on every upsert.
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

  return { action: "upserted", task_id: taskId, idempotency_key: idempotencyKey };
}
