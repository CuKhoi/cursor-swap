import ast
import io
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError

import pytest

from cursorswap import cli, i18n, usage


def test_catalog_matches_every_bash_message():
    bash = Path(__file__).resolve().parents[1].joinpath("cursorswap").read_text()
    count = 0
    for language, key, literal in re.findall(r"^MSG_(EN|VI)\[([^]]+)\]=(.*)$", bash, re.M):
        if literal.startswith("$'"):
            value = ast.literal_eval(literal[1:])
        else:
            value = literal[1:-1].replace(r'\$', '$').replace(r'\"', '"').replace(r'\\', '\\')
        assert getattr(i18n, "MSG_" + language)[key] == value, (language, key)
        count += 1
    assert count > 200


def test_substitution_and_fallback(monkeypatch):
    assert i18n.t("msg_saved_cli", "profile", "a@example.com", 2) == "Saved 'profile' (a@example.com) as slot 2"
    assert "usage %" in i18n.t("err_no_session_or_ide", "a", "api-key")
    monkeypatch.setattr(i18n, "LANG", "vi")
    assert i18n.t("msg_renumbered", 3) == "Đã đánh lại số slot cho 3 account, liền mạch từ 1..3."
    monkeypatch.setitem(i18n.MSG_VI, "fallback", "")
    monkeypatch.setitem(i18n.MSG_EN, "fallback", "English {1}% / {2}%")
    assert i18n.t("fallback", 25, 80) == "English 25% / 80%"
    monkeypatch.delitem(i18n.MSG_VI, "fallback")
    assert i18n.t("fallback", 1, 2) == "English 1% / 2%"
    monkeypatch.setitem(i18n.MSG_EN, "fallback", "")
    assert i18n.t("fallback") == "fallback"
    assert i18n.t("unknown_key") == "unknown_key"


class Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status


def test_usage_request_and_rounding(monkeypatch):
    def urlopen(request, timeout):
        assert request.full_url == usage.URL
        assert request.method == "POST"
        assert request.data == b"{}"
        assert request.get_header("Authorization") == "Bearer fake-token"
        assert request.get_header("Content-type") == "application/json"
        assert request.get_header("Connect-protocol-version") == "1"
        assert timeout == 4
        return Response(json.dumps({"planUsage": {"totalPercentUsed": 70.15,
                        "autoPercentUsed": 90, "apiPercentUsed": 0}}).encode())
    monkeypatch.setattr(usage.request, "urlopen", urlopen)
    assert usage.summary("fake-token") == ("total: 70.2%  auto: 90%  api: 0%", True)


@pytest.mark.parametrize("status,key", [(401, "usage_err_revoked"), (403, "usage_err_revoked"),
                                         (429, "usage_err_http"), (500, "usage_err_http"), (302, "usage_err_http")])
def test_usage_http_errors(monkeypatch, status, key):
    def fail(*args, **kwargs):
        raise HTTPError(usage.URL, status, "failed", {}, io.BytesIO())
    monkeypatch.setattr(usage.request, "urlopen", fail)
    assert usage.summary("token") == (i18n.t(key, status), False)
    monkeypatch.setattr(usage.request, "urlopen", lambda *a, **kw: Response(b"", status))
    assert usage.summary("token") == (i18n.t(key, status), False)


@pytest.mark.parametrize("error", [URLError("offline"), TimeoutError(), OSError("offline")])
def test_usage_network(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(usage.request, "urlopen", fail)
    assert usage.summary("token") == (i18n.t("usage_err_network"), False)
    assert usage.field("token") == i18n.t("usage_err_network")


@pytest.mark.parametrize("body", [b"bad-json", b"{}", b"null", b'[]', b'{"planUsage":null}',
    b'{"planUsage": {"totalPercentUsed": false}}', b'{"planUsage": {"totalPercentUsed": "70"}}',
    b'{"planUsage": {"totalPercentUsed": NaN}}', b'{"planUsage": {"totalPercentUsed": 1e300}}'])
def test_usage_unexpected_shape(monkeypatch, body):
    monkeypatch.setattr(usage.request, "urlopen", lambda *a, **kw: Response(body))
    assert usage.summary("token") == (i18n.t("usage_err_shape"), False)


def test_usage_zero_and_missing_optional_fields(monkeypatch):
    monkeypatch.setattr(usage.request, "urlopen", lambda *a, **kw: Response(b'{"planUsage":{"totalPercentUsed":0}}'))
    assert usage.summary("token") == ("total: 0%  auto: 0%  api: 0%", True)


def test_usage_no_token():
    assert usage.summary("") == (i18n.t("usage_err_no_token"), False)
    assert cli.main(["usage"]) == 1


def test_usage_active_cli_and_ide_failure(isolated, monkeypatch, capsys):
    isolated["secrets"]["cursor-access-token"] = "fake-token"
    monkeypatch.setattr(usage.request, "urlopen", lambda *a, **kw: Response(b'{"planUsage":{"totalPercentUsed":5}}'))
    assert cli.main(["usage"]) == 0
    assert "(cli active): total: 5%" in capsys.readouterr().out
    monkeypatch.setattr(usage.request, "urlopen", lambda *a, **kw: Response(b"", 403))
    assert cli.main(["usage"]) == 1
    assert "session rejected" in capsys.readouterr().err
