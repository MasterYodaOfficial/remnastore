"""Configure self-hosted GoTrue's custom:yandex using a server-only credential file.

Run on the Docker host. No credentials are printed; a short-lived admin JWT is
derived in memory from the running Auth container's existing signing secret.
"""

import argparse
import base64
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth-container", required=True)
    parser.add_argument("--auth-url", default="http://127.0.0.1:9999")
    parser.add_argument("--credentials-file", type=Path, required=True)
    parser.add_argument("--userinfo-url", required=True)
    parser.add_argument("--enable", action="store_true")
    args = parser.parse_args()
    if not args.userinfo_url.startswith("https://"):
        parser.error("userinfo-url must use HTTPS")
    credentials = json.loads(args.credentials_file.read_text())
    if not credentials.get("client_id") or not credentials.get("client_secret"):
        parser.error("credentials file requires client_id and client_secret")
    container = json.loads(
        subprocess.check_output(["docker", "inspect", args.auth_container])
    )[0]
    env = dict(item.split("=", 1) for item in container["Config"]["Env"])

    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    header = encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = encode(
        json.dumps(
            {
                "role": "service_role",
                "aud": env.get("GOTRUE_JWT_AUD", "authenticated"),
                "iat": int(time.time()),
                "exp": int(time.time()) + 120,
            }
        ).encode()
    )
    signing_input = f"{header}.{payload}"
    signature = encode(
        hmac.new(
            env["GOTRUE_JWT_SECRET"].encode(), signing_input.encode(), hashlib.sha256
        ).digest()
    )
    headers = {
        "Authorization": f"Bearer {signing_input}.{signature}",
        "Content-Type": "application/json",
    }
    base = args.auth_url.rstrip("/") + "/admin/custom-providers"
    existing = None
    try:
        with urlopen(
            Request(base + "/custom:yandex", headers=headers), timeout=15
        ) as response:
            existing = json.load(response)
    except HTTPError as exc:
        if exc.code != 404:
            raise SystemExit(f"Provider lookup failed: HTTP {exc.code}") from None
    data = {
        "provider_type": "oauth2",
        "identifier": "custom:yandex",
        "name": "Yandex ID",
        "client_id": credentials["client_id"],
        "client_secret": credentials["client_secret"],
        "authorization_url": "https://oauth.yandex.ru/authorize",
        "token_url": "https://oauth.yandex.ru/token",
        "userinfo_url": args.userinfo_url,
        # Yandex's application already defines login:email and login:info. Omit
        # scope so GoTrue does not send its space-separated OAuth scope format.
        "scopes": [],
        "pkce_enabled": True,
        "email_optional": False,
        "enabled": args.enable,
    }
    if existing:
        # Provider type and identifier are immutable on update.
        del data["provider_type"]
        del data["identifier"]
    request = Request(
        base + ("/custom:yandex" if existing else ""),
        data=json.dumps(data).encode(),
        headers=headers,
        method="PUT" if existing else "POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as exc:
        # Do not print an upstream response that might echo submitted secrets.
        raise SystemExit(f"Provider configuration failed: HTTP {exc.code}") from None
    print("Configured custom:yandex; enabled:", result.get("enabled"))


if __name__ == "__main__":
    main()
