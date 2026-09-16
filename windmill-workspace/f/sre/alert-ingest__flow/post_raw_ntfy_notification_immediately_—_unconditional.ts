export async function main(
  payload: any,
  ntfy_base_url: string,
  ntfy_token: string
) {
  const alerts: any[] = payload.alerts ?? [];
  const status: string = payload.status ?? "firing";
  const commonLabels: any = payload.commonLabels ?? {};
  const commonAnnotations: any = payload.commonAnnotations ?? {};
  const firstAlert = alerts[0] ?? {};
  const labels = firstAlert.labels ?? commonLabels;
  const annotations = firstAlert.annotations ?? commonAnnotations;

  const alertname: string = labels.alertname ?? "Unknown Alert";
  const severity: string = labels.severity ?? "warning";
  const namespace: string = labels.namespace ?? "";
  const summary: string = annotations.summary ?? alertname;
  const description: string = annotations.description ?? "";

  const topic =
    status === "resolved"
      ? "alerts-resolved"
      : severity === "critical"
      ? "alerts-critical"
      : "alerts-warning";

  const priority =
    status === "resolved" ? 3 : severity === "critical" ? 5 : 4;

  // No literal emoji in header values — HTTP headers must be Latin-1;
  // Windmill's bun runtime enforces that and throws "TypeError: Header
  // 'Title' has invalid value" on any non-Latin-1 char, which (since this
  // step has no continue_on_error) crashes the ENTIRE flow before ntfy,
  // the Kanban board write, or routing ever run. Confirmed live 2026-09-16
  // via a real flow run — every status/severity combination here maps to
  // an emoji, so this was breaking on every single alert. ntfy's own Tags
  // shortcode mechanism (ASCII names) is what actually renders an emoji
  // client-side — already used correctly two lines below and in the
  // sibling post_restic-check-repo_result_to_ntfy_thread.ts.
  const emojiTag =
    status === "resolved" ? "white_check_mark" : severity === "critical" ? "rotating_light" : "warning";
  const title = `${status === "resolved" ? "RESOLVED" : "FIRING"}: ${alertname}`;

  const parts: string[] = [summary];
  if (description && description !== summary) parts.push(description);
  if (namespace) parts.push(`namespace: ${namespace}`);
  if (alerts.length > 1) parts.push(`(${alerts.length} alerts in group)`);
  const message = parts.join("\n");

  const headers: Record<string, string> = {
    Title: title,
    Priority: String(priority),
    Tags: `${emojiTag},${severity},${status}`,
    "Content-Type": "text/plain",
  };
  if (ntfy_token) headers["Authorization"] = `Bearer ${ntfy_token}`;

  const resp = await fetch(`${ntfy_base_url}/${topic}`, {
    method: "POST",
    headers,
    body: message,
  });

  return { topic, title, priority, ntfy_status: resp.status, ok: resp.ok };
}
