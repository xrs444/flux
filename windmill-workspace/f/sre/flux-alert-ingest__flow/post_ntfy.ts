// Flux generic-provider Event shape (github.com/fluxcd/pkg/apis/event —
// stable across Flux v1/v2, NOT the Alertmanager webhook shape used by
// f/sre/alert-ingest__flow): {involvedObject, severity, reason, message,
// timestamp, reportingController}. Kept as its own flow rather than reusing
// alert-ingest — see sealedsecret-flux-alert-webhook.yaml for why.
export async function main(
  payload: any,
  ntfy_base_url: string,
  ntfy_token: string
) {
  const involved = payload.involvedObject ?? {};
  const kind: string = involved.kind ?? "Resource";
  const name: string = involved.name ?? "unknown";
  const namespace: string = involved.namespace ?? "flux-system";
  const reason: string = payload.reason ?? "ReconciliationFailed";
  const message: string = payload.message ?? "";

  // No literal emoji in header values — HTTP headers must be Latin-1, and a
  // fetch() implementation that enforces that (confirmed live 2026-09-16:
  // Windmill's bun runtime throws "TypeError: Header 'Title' has invalid
  // value" on this exact pattern in the sibling alert-ingest__flow's
  // post_ntfy.ts) will crash the whole step. ntfy's own Tags shortcode
  // mechanism (ASCII names, e.g. "rotating_light") is what actually renders
  // an emoji client-side — this is the same pattern already used correctly
  // in alert-ingest__flow/post_restic-check-repo_result_to_ntfy_thread.ts.
  const title = `FLUX FAILURE: ${kind}/${name}`;
  const body = [`namespace: ${namespace}`, `reason: ${reason}`, message]
    .filter(Boolean)
    .join("\n");

  const headers: Record<string, string> = {
    Title: title,
    Priority: "5",
    Tags: "rotating_light,flux,error",
    "Content-Type": "text/plain",
  };
  if (ntfy_token) headers["Authorization"] = `Bearer ${ntfy_token}`;

  const resp = await fetch(`${ntfy_base_url}/alerts-critical`, {
    method: "POST",
    headers,
    body,
  });

  return { title, ntfy_status: resp.status, ok: resp.ok };
}
