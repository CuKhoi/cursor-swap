"""Best-effort usage RPC; errors are displayable, never an empty field."""
import json
import math
from http.client import HTTPException
from decimal import Decimal, ROUND_HALF_UP
from urllib import request, error

from . import cli_session, ide
from .colors import muted, sev_pct
from .i18n import t
from .store import read_json

URL = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"


def any_access_token(directory):
    if (directory / "access-token").is_file():
        return (directory / "access-token").read_text().rstrip("\n")
    if (directory / "ide-auth.json").is_file():
        return ide.row_value(read_json(directory / "ide-auth.json"), "accessToken")
    return ""


def effective_access_token(store, directory):
    meta = read_json(directory / "meta.json")
    if meta["type"] == "session" and meta["email"] == cli_session.current_email() and cli_session.has_session():
        token = cli_session.secret_get("cursor-access-token")
        if token:
            return token
    if meta.get("ide_email") and meta["ide_email"] == ide.current_email(store):
        token = ide.live_token()
        if token:
            return token
    return any_access_token(directory)


def summary(token):
    if not token:
        return t("usage_err_no_token"), False
    req = request.Request(URL, data=b"{}", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "Connect-Protocol-Version": "1"}, method="POST")
    try:
        with request.urlopen(req, timeout=4) as response:
            status = response.status
            body = response.read()
    except error.HTTPError as exc:
        status, body = exc.code, b""
        exc.close()
    except (OSError, error.URLError, ValueError, HTTPException):
        return t("usage_err_network"), False
    if status in (401, 403):
        return t("usage_err_revoked"), False
    if status != 200:
        return t("usage_err_http", status), False
    try:
        plan = json.loads(body)["planUsage"]
        if plan.get("totalPercentUsed") is None or plan.get("totalPercentUsed") is False:
            raise ValueError("missing total")
        values = [plan.get(key) or 0 for key in ("totalPercentUsed", "autoPercentUsed", "apiPercentUsed")]
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in values):
            raise ValueError("non-numeric usage")
        # jq's round rounds halves away from zero; omit a trailing .0 as jq does.
        values = [format(Decimal(str(v)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f").removesuffix(".0") for v in values]
    except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError):
        return t("usage_err_shape"), False
    return "  ".join(f"{muted(name + ':')} {sev_pct(value)}" for name, value in zip(("total", "auto", "api"), values)), True


def field(token):
    text, ok = summary(token)
    return text if ok else muted(text)
