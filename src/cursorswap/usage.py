"""Best-effort usage RPC; errors are displayable, never an empty field."""
import json
import math
from http.client import HTTPException
from decimal import Decimal, ROUND_HALF_UP
from urllib import request, error

from . import ide
from .colors import muted, sev_pct
from .i18n import t

URL = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"


def effective_access_token(directory):
    """The live token for the account Cursor.app is signed into right now (the IDE
    rotates it silently, so the snapshot can be stale), else the saved snapshot's."""
    live = ide.live_token()
    sub = ide.snapshot_sub(directory)
    if live and sub and ide.jwt_sub(live) == sub:
        return live
    return ide.row_value(ide.snapshot_rows(directory), "accessToken")


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
        return t("usage_err_rejected_ide"), False
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
