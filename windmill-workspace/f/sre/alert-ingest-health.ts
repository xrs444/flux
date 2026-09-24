// Self-monitoring for f/sre/alert-ingest and f/sre/flux-alert-ingest's
// kanban_card_upsert step. That step runs with continue_on_error: true (by
// design — a kanban-write failure must never block ntfy or runbook routing),
// which means a 100%-failure rate is otherwise invisible: the parent flow
// job reports success:true on every run even while every single
// kanban_card_upsert step throws. This is exactly what happened from
// 2026-09-16 (pipeline went live) to 2026-09-24 (discovered during an ops
// board triage pass) — `hermes kanban complete` on a `triage` card is a
// guaranteed failure (see kanban_card_upsert.ts), and nothing ever surfaced
// it. See .wolf/buglog.json for the incident.
//
// There is no Prometheus metric for this — confirmed live, Prometheus has
// zero `windmill_*` series; the only Windmill signal it has is the generic
// `up{job="windmill"}` scrape check, which says nothing about individual
// script outcomes. So this checks Windmill's own job history directly via
// its REST API instead of a PrometheusRule.
//
// Scheduled hourly (see alert-ingest-health.schedule.yaml). Reads WM_TOKEN
// and BASE_INTERNAL_URL from the worker's own environment — both are always
// present in a Windmill job's environment, no resource/variable needed.

interface JobListItem {
  id: string;
  script_path?: string;
  success?: boolean;
}

async function listFailedSteps(
  baseUrl: string,
  token: string,
  workspace: string,
  scriptPathExact: string,
  createdAfterIso: string
): Promise<JobListItem[]> {
  const url = new URL(`${baseUrl}/api/w/${workspace}/jobs/list`);
  url.searchParams.set("script_path_exact", scriptPathExact);
  url.searchParams.set("success", "false");
  url.searchParams.set("is_flow_step", "true");
  url.searchParams.set("created_after", createdAfterIso);
  url.searchParams.set("per_page", "100");

  const resp = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    throw new Error(
      `jobs/list failed for ${scriptPathExact} (HTTP ${resp.status}): ${await resp.text()}`
    );
  }
  return (await resp.json()) as JobListItem[];
}

export async function main(
  ntfy_base_url: string,
  ntfy_token: string,
  lookback_minutes: number = 90
) {
  const token = process.env.WM_TOKEN ?? "";
  const baseUrl = process.env.BASE_INTERNAL_URL ?? process.env.BASE_URL ?? "";
  const workspace = process.env.WM_WORKSPACE ?? "xrs444";
  if (!token || !baseUrl) {
    throw new Error(
      `missing WM_TOKEN or BASE_INTERNAL_URL/BASE_URL in worker environment (token=${!!token}, baseUrl=${!!baseUrl})`
    );
  }

  const createdAfter = new Date(Date.now() - lookback_minutes * 60_000).toISOString();

  const watchedSteps = [
    "f/sre/alert-ingest/kanban_card_upsert",
    "f/sre/flux-alert-ingest/kanban_card_upsert",
  ];

  const results = await Promise.all(
    watchedSteps.map((path) => listFailedSteps(baseUrl, token, workspace, path, createdAfter))
  );

  const failures = watchedSteps
    .map((path, i) => ({ path, count: results[i].length }))
    .filter((r) => r.count > 0);

  if (failures.length === 0) {
    return { action: "ok", checked: watchedSteps, lookback_minutes };
  }

  const lines = failures.map((f) => `${f.path}: ${f.count} failure(s)`);
  const message = [
    `kanban_card_upsert has been failing silently (continue_on_error hides it from the flow's own status).`,
    ...lines,
    `Check: wmill job list --script-path <path> --failed, or the Windmill UI.`,
  ].join("\n");

  const headers: Record<string, string> = {
    Title: "alert-ingest: kanban board write failing",
    Priority: "4",
    Tags: "warning,windmill,kanban",
    "Content-Type": "text/plain",
  };
  if (ntfy_token) headers["Authorization"] = `Bearer ${ntfy_token}`;

  const resp = await fetch(`${ntfy_base_url}/alerts-warning`, {
    method: "POST",
    headers,
    body: message,
  });

  return { action: "alerted", failures, ntfy_status: resp.status, ntfy_ok: resp.ok };
}
