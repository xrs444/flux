export async function main(payload: any) {
  const alertname = payload.commonLabels?.alertname ?? payload.alerts?.[0]?.labels?.alertname ?? "unknown";
  // TODO Phase A step 9: wire to f/sre/runbooks/backup/borg-check-repo
  console.log(`[route] backup alert: ${alertname} — runbook pending step 9`);
  return {
    action: "runbook_queued",
    runbook: "f/sre/runbooks/backup/borg-check-repo",
    alertname,
    note: "runbook stub — deploy in Phase A step 9",
  };
}