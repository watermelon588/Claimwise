"""Client for the connector gateway (connectors/app.py): submit an approved claim and read its status.

Mock only. The gateway holds the user's consent per case; the backend binds one case to one claim
thread after the user pastes the connection code shown on the gateway page. Standard library HTTP
keeps this free of new dependencies.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from app.config import get_settings


class ConnectorError(Exception):
    """A gateway failure with its HTTP status (0 when unreachable) and short error code."""

    def __init__(self, status: int, code: str):
        """Store the status and code; no upstream text is kept."""
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code

    @property
    def unclear(self) -> bool:
        """True when a write may or may not have happened, so the claim must be looked up before retrying."""
        return self.status == 0 or self.status >= 500


def _call(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
    """One JSON request to the gateway with the server bearer key.

    Raises:
        ConnectorError: not configured (0, NOT_CONFIGURED), unreachable (0, UNREACHABLE) or an HTTP error.
    """
    settings = get_settings()
    if not settings.connector_url or not settings.connector_agent_key:
        raise ConnectorError(0, "NOT_CONFIGURED")
    request = urllib.request.Request(
        settings.connector_url.rstrip("/") + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {settings.connector_agent_key}", "Content-Type": "application/json",
                 **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read(1024 * 1024))
    except urllib.error.HTTPError as exc:
        try:
            code = json.loads(exc.read(4096))["detail"]["code"]
        except (ValueError, KeyError, TypeError):
            code = "GATEWAY_ERROR"
        raise ConnectorError(exc.code, code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConnectorError(0, "UNREACHABLE") from exc


def _case(case_id: str) -> str:
    """URL path for one consented case (quoted so a case id can never change the route)."""
    return "/agent/cases/" + urllib.parse.quote(case_id, safe="")


def connected_tools(case_id: str) -> list[str]:
    """Tool names the user has consented to for this case."""
    return [tool["name"] for tool in _call("GET", _case(case_id) + "/tools")["tools"]]


def submit_claim(case_id: str, submission: dict, idempotency_key: str) -> dict:
    """Write: submit an approved claim. The same key always returns the same claim."""
    return _call("POST", _case(case_id) + "/claims", submission, {"Idempotency-Key": idempotency_key})["data"]


def find_claims(case_id: str, client_reference: str) -> list[dict]:
    """Claims the payer holds for our client reference (lost-response recovery)."""
    query = urllib.parse.urlencode({"client_reference": client_reference})
    return _call("GET", _case(case_id) + "/claims?" + query)["data"]


def read_claim(case_id: str, claim_id: str) -> dict:
    """Status, queries, decision and payments of one submitted claim."""
    return _call("GET", _case(case_id) + "/claims/" + urllib.parse.quote(claim_id, safe=""))["data"]


def answer_query(case_id: str, claim_id: str, documents: list[dict]) -> dict:
    """Write: send the documents that answer the open query on a submitted claim (metadata only)."""
    path = _case(case_id) + "/claims/" + urllib.parse.quote(claim_id, safe="") + "/documents"
    return _call("POST", path, {"documents": documents})["data"]
