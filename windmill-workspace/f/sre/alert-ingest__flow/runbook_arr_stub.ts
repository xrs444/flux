export async function main(payload: any) {
  const alertname = payload.commonLabels?.alertname ?? payload.alerts?.[0]?.labels?.alertname ?? "unknown";
  // TODO Phase A step 9: wire to f/sre/runbooks/restart-arr-queue
  console.log(`[route] arr queue alert: ${alertname} — runbook pending step 9`);
  return {
    action: "runbook_queued",
    runbook: "f/sre/runbooks/restart-arr-queue",
    alertname,
    note: "runbook stub — deploy in Phase A step 9",
  };
}