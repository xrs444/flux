export async function main(payload: any) {
  const alertname = payload.commonLabels?.alertname ?? payload.alerts?.[0]?.labels?.alertname ?? "unknown";
  const severity = payload.commonLabels?.severity ?? payload.alerts?.[0]?.labels?.severity ?? "unknown";
  console.log(`[route] no runbook match for ${alertname} (${severity}) — Phase C enrichment pending`);
  return { action: "no_runbook", alertname, severity, message: "No deterministic runbook match. Phase C LLM enrichment (f/sre/hermes-enrich) will handle this." };
}