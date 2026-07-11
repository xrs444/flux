export async function main(
  arr_app: "sonarr" | "radarr" | "lidarr",
  dry_run: boolean = true,
  sonarr_api_key: string,
  radarr_api_key: string,
  lidarr_api_key: string
) {
  const apps: Record<string, { base: string; key: string; apiVersion: string }> = {
    sonarr: { base: "http://sonarr.sonarr.svc.cluster.local:8989", key: sonarr_api_key, apiVersion: "v3" },
    radarr: { base: "http://radarr.radarr.svc.cluster.local:7878", key: radarr_api_key, apiVersion: "v3" },
    lidarr: { base: "http://lidarr.lidarr.svc.cluster.local:8686", key: lidarr_api_key, apiVersion: "v1" },
  };
  const target = apps[arr_app];
  if (!target) throw new Error(`Unknown arr_app: ${arr_app}`);

  const queueResp = await fetch(
    `${target.base}/api/${target.apiVersion}/queue?pageSize=200&includeUnknownSeriesItems=true`,
    { headers: { "X-Api-Key": target.key } }
  );
  if (!queueResp.ok) {
    throw new Error(`Failed to fetch ${arr_app} queue: ${queueResp.status} ${await queueResp.text()}`);
  }
  const queue: any = await queueResp.json();
  const records: any[] = queue.records ?? [];

  const stuck = records.filter((r) => {
    const status = (r.status ?? "").toLowerCase();
    const hasErrors = Array.isArray(r.statusMessages) && r.statusMessages.length > 0;
    return status === "warning" || status === "failed" || hasErrors;
  });

  if (stuck.length === 0) {
    return { action: "noop", arr_app, message: "No stuck items in queue.", total_in_queue: records.length };
  }

  const results: any[] = [];
  for (const item of stuck) {
    if (dry_run) {
      results.push({
        id: item.id,
        title: item.title,
        status: item.status,
        action: "would_remove_and_retry",
      });
      continue;
    }
    const delResp = await fetch(
      `${target.base}/api/${target.apiVersion}/queue/${item.id}?removeFromClient=true&blocklist=false`,
      { method: "DELETE", headers: { "X-Api-Key": target.key } }
    );
    results.push({
      id: item.id,
      title: item.title,
      status: item.status,
      action: "removed",
      ok: delResp.ok,
    });
  }

  return {
    action: dry_run ? "dry_run" : "executed",
    arr_app,
    stuck_count: stuck.length,
    results,
  };
}
