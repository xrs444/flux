"""
Synthetic Hermes LLM-Reachability Monitor
===========================================
Calls each Hermes instance's own OpenAI-compatible gateway
(POST /v1/chat/completions) with a minimal prompt and verifies a real
assistant response comes back. Catches exactly the bug-956 failure mode:
the gateway itself stays up and responds to other calls, but the model
is misconfigured or its backend is unreachable, so completions fail or
silently fall back to an unintended model. Pushes pass/fail + latency
metrics to Prometheus Pushgateway so alerts fire the moment an instance
can't produce a real completion.

Variables required in Windmill (xrs444 workspace):
- f/monitoring/hermes_t_api_key (sensitive)
- f/monitoring/hermes_s_api_key (sensitive)
- f/monitoring/hermes_k_api_key (sensitive)

Schedule: every 10 minutes.
"""

import time

import requests
import wmill

PUSHGATEWAY_URL = "http://pushgateway.monitoring.svc.cluster.local:9091"

INSTANCES = [
    {"name": "hermes-t", "url": "https://hermes-t.xrs444.net/v1/chat/completions", "key_var": "f/monitoring/hermes_t_api_key"},
    {"name": "hermes-s", "url": "https://hermes-s.xrs444.net/v1/chat/completions", "key_var": "f/monitoring/hermes_s_api_key"},
    {"name": "hermes-k", "url": "https://hermes-k.xrs444.net/v1/chat/completions", "key_var": "f/monitoring/hermes_k_api_key"},
]

PROMPT = "Reply with exactly one word: pong"
# xcog1's MLX inference can be slow on a cold model swap between instances
# (observed up to ~42s warm during manual verification 2026-09-16); budget
# generously so a slow-but-working response isn't misreported as a failure.
TIMEOUT = 90


def check_instance(inst: dict) -> tuple[bool, str, float]:
    api_key = wmill.get_variable(inst["key_var"])
    t0 = time.monotonic()
    try:
        resp = requests.post(
            inst["url"],
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "default",
                "messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": 10,
            },
            timeout=TIMEOUT,
        )
    except requests.Timeout:
        return False, f"timeout after {TIMEOUT}s", time.monotonic() - t0
    except requests.RequestException as exc:
        return False, f"network error: {exc}", time.monotonic() - t0
    duration = time.monotonic() - t0
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}", duration
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        return False, f"malformed response: {exc} -- {resp.text[:200]}", duration
    if not content or not content.strip():
        return False, "empty completion content", duration
    return True, content.strip()[:50], duration


def push_metrics(metrics: list[dict]) -> None:
    lines = (
        ["# HELP synthetic_hermes_success 1=ok 0=fail", "# TYPE synthetic_hermes_success gauge"]
        + [f'synthetic_hermes_success{{instance="{m["instance"]}"}} {m["success"]}' for m in metrics]
        + [
            "# HELP synthetic_hermes_duration_seconds chat completion round-trip time",
            "# TYPE synthetic_hermes_duration_seconds gauge",
        ]
        + [f'synthetic_hermes_duration_seconds{{instance="{m["instance"]}"}} {m["duration"]:.4f}' for m in metrics]
    )
    requests.put(
        f"{PUSHGATEWAY_URL}/metrics/job/synthetic_hermes",
        data="\n".join(lines) + "\n",
        headers={"Content-Type": "text/plain; version=0.0.4"},
        timeout=10,
    ).raise_for_status()


def main() -> dict:
    metrics, failures = [], []
    for inst in INSTANCES:
        ok, detail, duration = check_instance(inst)
        print(f"  [{'OK  ' if ok else 'FAIL'}] {inst['name']:<10} {detail} ({duration:.2f}s)")
        metrics.append({"instance": inst["name"], "success": 1 if ok else 0, "duration": duration})
        if not ok:
            failures.append(inst["name"])
    print(f"\nPushing {len(metrics)} metrics...")
    push_metrics(metrics)
    summary = {
        "total": len(INSTANCES),
        "ok": len(metrics) - len(failures),
        "failed": len(failures),
        "failing_instances": failures,
    }
    print(f"Result: {summary['ok']}/{summary['total']} OK")
    if failures:
        raise RuntimeError(f"Hermes LLM reachability failures: {', '.join(failures)}")
    return summary
