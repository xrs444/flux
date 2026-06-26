"""
Synthetic SSO Login Monitor
============================
Authenticates the `monitoring` Kanidm account (password + TOTP) and performs
an OAuth2 PKCE authorize round-trip against each app's Kanidm client. Pushes
pass/fail metrics to Prometheus Pushgateway so alerts fire the moment a login
breaks.

What this tests:
- Kanidm is reachable and the monitoring account is not locked
- Each app's OAuth2 client is registered in Kanidm
- The monitoring account has scope-map access to each app
- Each app's redirect_uri is registered (Kanidm validates at the authorize step)

What this does NOT test (Phase 2):
- Token exchange (doesn't catch rotated client secrets; needs client_id+secret)

Prometheus metrics pushed (job=synthetic_login, per-app grouping):
- synthetic_login_success{app}        : 1 = ok, 0 = failed
- synthetic_login_duration_seconds{app}: wall-clock time for the authorize step
- Pushgateway auto-adds push_time_seconds{job="synthetic_login"} (dead-man switch)

Variables required in Windmill (admins workspace):
- u/admin/monitoring_kanidm_password  (sensitive) -- account password
- u/admin/monitoring_kanidm_totp      (sensitive) -- base32 TOTP seed from setup

Schedule: every 10 minutes.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

import requests
import wmill

KANIDM_URL = "https://idm.xrs444.net"
PUSHGATEWAY_URL = "http://pushgateway.monitoring.svc.cluster.local:9091"
KANIDM_USERNAME = "monitoring"

APPS = [
    {
        "name": "paperless",
        "client_id": "oauth2_paperless",
        "redirect_uri": "https://paperless.xrs444.net/accounts/oidc/kanidm/login/callback/",
        "scopes": "openid profile email",
    },
    {
        "name": "mealie",
        "client_id": "oauth2_mealie",
        "redirect_uri": "https://mealie.xrs444.net/login",
        "scopes": "openid profile email",
    },
    {
        "name": "netbox",
        "client_id": "oauth2_netbox",
        "redirect_uri": "https://netbox.xrs444.net/oauth/complete/oidc/",
        "scopes": "openid profile email",
    },
    {
        "name": "immich",
        "client_id": "oauth2_immich",
        "redirect_uri": "https://immich.xrs444.net/auth/login",
        "scopes": "openid profile email",
    },
    {
        "name": "romm",
        "client_id": "oauth2_romm",
        "redirect_uri": "https://romm.xrs444.net/oauth/callback",
        "scopes": "openid profile email",
    },
    {
        "name": "audiobookshelf",
        "client_id": "oauth2_audiobookshelf",
        "redirect_uri": "https://audiobookshelf.xrs444.net/audiobookshelf/auth/openid/callback",
        "scopes": "openid profile email",
    },
    {
        "name": "booklore",
        "client_id": "oauth2_booklore",
        "redirect_uri": "https://booklore.xrs444.net/oauth2-callback",
        "scopes": "openid profile email",
    },
    {
        "name": "matrix",
        "client_id": "oauth2_matrix",
        "redirect_uri": "https://matrix.xrs444.net/_synapse/client/oidc/callback",
        "scopes": "openid profile email",
    },
    {
        "name": "seatable",
        "client_id": "oauth2_seatable",
        "redirect_uri": "https://seatable.xrs444.net/oauth/callback/",
        "scopes": "openid profile email",
    },
    {
        "name": "linkwarden",
        "client_id": "oauth2_linkwarden",
        "redirect_uri": "https://linkwarden.xrs444.net/api/v1/auth/callback/keycloak",
        "scopes": "openid profile email",
    },
    {
        "name": "termix",
        "client_id": "oauth2_termix",
        "redirect_uri": "https://termix.xrs444.net/users/oidc/callback",
        "scopes": "openid profile email",
    },
    {
        "name": "warpgate",
        "client_id": "oauth2_warpgate",
        "redirect_uri": "https://warpgate.xrs444.net/@warpgate/api/sso/return",
        "scopes": "openid email",
    },
    {
        "name": "manyfold",
        "client_id": "oauth2_manyfold",
        "redirect_uri": "https://manyfold.xrs444.net/users/auth/openid_connect/callback",
        "scopes": "openid profile email",
    },
    {
        "name": "windmill",
        "client_id": "oauth2_windmill",
        "redirect_uri": "https://windmill.xrs444.net/user/login_callback/kanidm",
        "scopes": "openid profile email",
    },
    {
        "name": "longhorn",
        "client_id": "oauth2_longhorn",
        "redirect_uri": "https://longhorn.xrs444.net/oauth2/callback",
        "scopes": "openid profile email groups",
    },
]


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _totp_now(secret_b32: str, interval: int = 30) -> int:
    """RFC 6238 TOTP — pure stdlib."""
    key = base64.b32decode(secret_b32.upper().replace(" ", ""))
    counter = int(time.time()) // interval
    msg = struct.pack(">Q", counter)
    mac = hmac.new(key, msg, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFF_FFFF
    return code % 1_000_000


def kanidm_auth(password: str, totp_secret: str) -> tuple[requests.Session, str]:
    """
    Kanidm passwordmfa flow (confirmed by probing the live API):
      init -> begin "passwordmfa" -> cred totp -> cred password -> success
    TOTP is requested FIRST, then password.
    """
    session = requests.Session()

    session.post(f"{KANIDM_URL}/v1/auth", json={"step": {"init": KANIDM_USERNAME}}, timeout=10).raise_for_status()
    session.post(f"{KANIDM_URL}/v1/auth", json={"step": {"begin": "passwordmfa"}}, timeout=10).raise_for_status()

    # Kanidm returns state.continue=["totp"] after begin -- submit TOTP first
    code = _totp_now(totp_secret)
    r3 = session.post(f"{KANIDM_URL}/v1/auth", json={"step": {"cred": {"totp": code}}}, timeout=10)
    r3.raise_for_status()

    state = r3.json().get("state", {})
    if "success" in state:
        return session, state["success"]
    if "continue" not in state:
        raise RuntimeError(f"Unexpected state after TOTP: {r3.text[:300]}")

    # Now submit password
    r4 = session.post(f"{KANIDM_URL}/v1/auth", json={"step": {"cred": {"password": password}}}, timeout=10)
    r4.raise_for_status()

    token = r4.json().get("state", {}).get("success")
    if not token:
        raise RuntimeError(f"No token after password step: {r4.text[:300]}")
    return session, token


def check_authorize(session: requests.Session, token: str, app: dict) -> tuple[bool, str]:
    _, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": app["client_id"],
        "redirect_uri": app["redirect_uri"],
        "scope": app["scopes"],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    try:
        resp = session.get(
            f"{KANIDM_URL}/oauth2/authorise",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            allow_redirects=False,
            timeout=15,
        )
    except requests.Timeout:
        return False, "timeout"
    except requests.RequestException as exc:
        return False, f"network error: {exc}"

    location = resp.headers.get("Location", "")
    if resp.status_code == 302:
        if "error=" in location:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
            error = qs.get("error", ["unknown"])[0]
            desc = qs.get("error_description", [""])[0]
            return False, f"oauth2 error={error} -- {desc or location[:120]}"
        return True, f"302 -> {location[:80] or '(no location)'}"
    if resp.status_code == 200:
        body = resp.text
        if "authorise/permit" in body:
            return True, "200 consent page"
        return True, f"200: {body[:80].replace(chr(10), ' ')}"
    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"


def push_metrics(metrics: list[dict]) -> None:
    lines = [
        "# HELP synthetic_login_success 1=ok 0=fail",
        "# TYPE synthetic_login_success gauge",
        *[f'synthetic_login_success{{app="{m["app"]}"}} {m["success"]}' for m in metrics],
        "# HELP synthetic_login_duration_seconds authorize request duration",
        "# TYPE synthetic_login_duration_seconds gauge",
        *[f'synthetic_login_duration_seconds{{app="{m["app"]}"}} {m["duration"]:.4f}' for m in metrics],
    ]
    requests.put(
        f"{PUSHGATEWAY_URL}/metrics/job/synthetic_login",
        data="\n".join(lines) + "\n",
        headers={"Content-Type": "text/plain; version=0.0.4"},
        timeout=10,
    ).raise_for_status()


def main() -> dict:
    password = wmill.get_variable("u/admin/monitoring_kanidm_password")
    totp_secret = wmill.get_variable("u/admin/monitoring_kanidm_totp")

    print(f"Authenticating to Kanidm as '{KANIDM_USERNAME}'...")
    try:
        session, token = kanidm_auth(password, totp_secret)
    except Exception as exc:
        print(f"CRITICAL: Kanidm auth failed: {exc}")
        try:
            push_metrics([{"app": a["name"], "success": 0, "duration": 0.0} for a in APPS])
        except Exception:
            pass
        raise

    print("Authenticated.\n")
    metrics, failures = [], []

    for app in APPS:
        t0 = time.monotonic()
        ok, detail = check_authorize(session, token, app)
        duration = time.monotonic() - t0
        print(f"  [{'OK  ' if ok else 'FAIL'}] {app['name']:<18} {detail} ({duration:.2f}s)")
        metrics.append({"app": app["name"], "success": 1 if ok else 0, "duration": duration})
        if not ok:
            failures.append(app["name"])

    print(f"\nPushing {len(metrics)} metrics...")
    push_metrics(metrics)

    summary = {"total": len(APPS), "ok": len(metrics) - len(failures), "failed": len(failures), "failing_apps": failures}
    print(f"Result: {summary['ok']}/{summary['total']} OK")
    if failures:
        raise RuntimeError(f"SSO failures: {', '.join(failures)}")
    return summary
