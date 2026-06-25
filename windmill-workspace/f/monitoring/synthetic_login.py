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

# ---------------------------------------------------------------------------
# App registry -- matches redirect URIs registered in
# nix/modules/services/kanidm/default.nix (kanidm-oauth2-redirect-urls service)
# and scope maps in nix/modules/services/kanidm/provision.nix.
#
# To add an app: add an entry here AND ensure the monitoring account has scope
# access (add to the right group in provision.nix) AND the redirect_uri is
# registered (add add_redirect line in default.nix).
# ---------------------------------------------------------------------------
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
    # Windmill -- gets its own critical-severity alert in Prometheus
    {
        "name": "windmill",
        "client_id": "oauth2_windmill",
        "redirect_uri": "https://windmill.xrs444.net/user/login_callback/kanidm",
        "scopes": "openid profile email",
    },
    # Forward-auth (Pattern B) -- tested via oauth2-proxy's Kanidm client
    {
        "name": "longhorn",
        "client_id": "oauth2_longhorn",
        "redirect_uri": "https://longhorn.xrs444.net/oauth2/callback",
        "scopes": "openid profile email groups",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge_S256)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _totp_now(secret_b32: str, interval: int = 30) -> int:
    """
    Generate the current TOTP code from a base32 seed (RFC 6238 / HMAC-SHA1).
    Pure stdlib -- no pyotp needed.
    """
    key = base64.b32decode(secret_b32.upper().replace(" ", ""))
    counter = int(time.time()) // interval
    msg = struct.pack(">Q", counter)
    mac = hmac.new(key, msg, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFF_FFFF
    return code % 1_000_000


# ---------------------------------------------------------------------------
# Kanidm authentication
# ---------------------------------------------------------------------------

def kanidm_auth(password: str, totp_secret: str) -> tuple[requests.Session, str]:
    """
    Authenticate via Kanidm's step-based API with password + TOTP.
    Returns (session, bearer_token).

    Flow:
      POST /v1/auth  {"step": {"init": "<username>"}}
      POST /v1/auth  {"step": {"begin": "passwordmfa"}}
      POST /v1/auth  {"step": {"cred": {"password": "<pw>"}}}
        -> state.success: done (MFA not enforced)
        -> state.continue: TOTP required
      POST /v1/auth  {"step": {"cred": {"totp": <6-digit-int>}}}
        -> state.success = bearer token
    """
    session = requests.Session()

    r1 = session.post(
        f"{KANIDM_URL}/v1/auth",
        json={"step": {"init": KANIDM_USERNAME}},
        timeout=10,
    )
    r1.raise_for_status()

    # Mechanism name confirmed via init response: state.choose = ["passwordmfa"]
    r2 = session.post(
        f"{KANIDM_URL}/v1/auth",
        json={"step": {"begin": "passwordmfa"}},
        timeout=10,
    )
    r2.raise_for_status()

    r3 = session.post(
        f"{KANIDM_URL}/v1/auth",
        json={"step": {"cred": {"password": password}}},
        timeout=10,
    )
    r3.raise_for_status()

    state = r3.json().get("state", {})

    if "success" in state:
        return session, state["success"]

    if "continue" not in state:
        raise RuntimeError(
            f"Kanidm auth: unexpected state after password step: {r3.text[:300]}"
        )

    code = _totp_now(totp_secret)
    r4 = session.post(
        f"{KANIDM_URL}/v1/auth",
        json={"step": {"cred": {"totp": code}}},
        timeout=10,
    )
    r4.raise_for_status()

    token = r4.json().get("state", {}).get("success")
    if not token:
        raise RuntimeError(
            f"Kanidm TOTP auth failed -- no token after TOTP step: {r4.text[:300]}"
        )
    return session, token


# ---------------------------------------------------------------------------
# Per-app authorize check
# ---------------------------------------------------------------------------

def check_authorize(
    session: requests.Session,
    token: str,
    app: dict,
) -> tuple[bool, str]:
    """
    Perform an OAuth2 PKCE authorize request for one app.
    Returns (success, detail_message).

    Success: any 302 without ?error=, or 200 consent page.
    Failure: 302 with ?error=, 4xx/5xx, network error.
    """
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
        return False, "timeout waiting for Kanidm"
    except requests.RequestException as exc:
        return False, f"network error: {exc}"

    location = resp.headers.get("Location", "")

    if resp.status_code == 302:
        if "error=" in location:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
            error = qs.get("error", ["unknown"])[0]
            desc = qs.get("error_description", [""])[0]
            return False, f"oauth2 error={error} -- {desc or location[:120]}"
        dest = location[:80] if location else "(no Location header)"
        return True, f"302 -> {dest}"

    if resp.status_code == 200:
        body = resp.text
        if "authorise/permit" in body or "/oauth2/authorise/permit" in body:
            return True, "200 consent page (client valid, account has scope access)"
        snippet = body[:120].replace("\n", " ")
        return True, f"200 (unknown body): {snippet}"

    return False, f"unexpected HTTP {resp.status_code}: {resp.text[:200]}"


# ---------------------------------------------------------------------------
# Pushgateway push
# ---------------------------------------------------------------------------

def push_metrics(metrics: list[dict]) -> None:
    """
    PUT all metrics to Pushgateway (replaces job=synthetic_login group).
    Pushgateway auto-adds push_time_seconds used by the dead-man switch alert.
    """
    lines: list[str] = [
        "# HELP synthetic_login_success Whether the synthetic login authorize check succeeded (1=ok, 0=fail)",
        "# TYPE synthetic_login_success gauge",
    ]
    for m in metrics:
        lines.append(f'synthetic_login_success{{app="{m["app"]}"}} {m["success"]}')

    lines += [
        "# HELP synthetic_login_duration_seconds Wall-clock time for the OAuth2 authorize request",
        "# TYPE synthetic_login_duration_seconds gauge",
    ]
    for m in metrics:
        lines.append(
            f'synthetic_login_duration_seconds{{app="{m["app"]}"}} {m["duration"]:.4f}'
        )

    resp = requests.put(
        f"{PUSHGATEWAY_URL}/metrics/job/synthetic_login",
        data="\n".join(lines) + "\n",
        headers={"Content-Type": "text/plain; version=0.0.4"},
        timeout=10,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> dict:
    """
    Windmill entrypoint. Raises on hard failure so Windmill marks the job failed.
    """
    password = wmill.get_variable("u/admin/monitoring_kanidm_password")
    totp_secret = wmill.get_variable("u/admin/monitoring_kanidm_totp")

    print(f"Authenticating to Kanidm as '{KANIDM_USERNAME}'...")
    try:
        session, token = kanidm_auth(password, totp_secret)
    except Exception as exc:
        print(f"CRITICAL: Kanidm authentication failed: {exc}")
        dead_metrics = [{"app": a["name"], "success": 0, "duration": 0.0} for a in APPS]
        try:
            push_metrics(dead_metrics)
        except Exception as push_exc:
            print(f"WARNING: also failed to push dead metrics: {push_exc}")
        raise

    print("Authenticated successfully.\n")

    metrics: list[dict] = []
    failures: list[str] = []

    for app in APPS:
        t0 = time.monotonic()
        ok, detail = check_authorize(session, token, app)
        duration = time.monotonic() - t0
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {app['name']:<18} {detail} ({duration:.2f}s)")
        metrics.append({"app": app["name"], "success": 1 if ok else 0, "duration": duration})
        if not ok:
            failures.append(app["name"])

    print(f"\nPushing {len(metrics)} metrics to Pushgateway...")
    push_metrics(metrics)
    print("Pushed.")

    summary = {
        "total": len(APPS),
        "ok": len(metrics) - len(failures),
        "failed": len(failures),
        "failing_apps": failures,
    }
    print(f"\nResult: {summary['ok']}/{summary['total']} OK")
    if failures:
        raise RuntimeError(f"SSO authorize failed for: {', '.join(failures)}")

    return summary
