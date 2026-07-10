export async function main(
  check_result: any,
  ntfy_base_url: string,
  ntfy_token: string
) {
  const ok = check_result?.success !== false;
  const title = ok ? "✅ restic-check-repo passed (xsvr2 offsite)" : "🔴 restic-check-repo FAILED (xsvr2 offsite)";
  const body = typeof check_result === "string" ? check_result : JSON.stringify(check_result).slice(0, 2000);

  const headers: Record<string, string> = {
    Title: title,
    Priority: ok ? "3" : "5",
    Tags: ok ? "white_check_mark" : "rotating_light",
    "Content-Type": "text/plain",
  };
  if (ntfy_token) headers["Authorization"] = `Bearer ${ntfy_token}`;

  const resp = await fetch(`${ntfy_base_url}/alerts-critical`, {
    method: "POST",
    headers,
    body,
  });

  return { ok: resp.ok, ntfy_status: resp.status };
}