export async function main(payload: any) {
  const alertname = payload.commonLabels?.alertname ?? payload.alerts?.[0]?.labels?.alertname ?? "unknown";
  console.log(`[route] arr queue alert: ${alertname} — runbook exists at f/sre/runbooks/restart-arr-queue but is not auto-invoked (mutates state; no ntfy Approve-button loop yet — Phase C)`);
  return { action: "runbook_available_not_invoked", runbook: "f/sre/runbooks/restart-arr-queue", alertname, note: "Run manually with dry_run=false, or wait for Phase C Approve-gated wiring." };
}