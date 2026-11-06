"""Project approved mock resources into safe case observations and demo email notices."""

import hashlib

from app import connector

LABELS = {
    "read_policy": "Insurance",
    "read_claim": "TPA",
    "read_discharge_summary": "Doctor portal",
    "read_bank_credits": "Bank",
}
MOCK_CLAIM_STATUSES = {
    "SUBMITTED", "UNDER_REVIEW", "QUERY_RAISED", "APPROVED", "PARTIAL", "REJECTED", "PAID", "CLOSED",
}


def summary(tool: str, data: dict) -> str:
    """Describe a schema-validated fixture without passing external free text to the model."""
    if tool == "read_policy":
        return f"Demo policy coverage retrieved. Sum insured: Rs {data['sum_insured'] / 100:,.2f}."
    if tool == "read_claim":
        status = data["status"].upper()
        stage = status.replace("_", " ").lower() if status in MOCK_CLAIM_STATUSES else "available"
        return f"Demo claim status: {stage}. Requests on file: {len(data['queries'])}."
    if tool == "read_discharge_summary":
        return "The demo discharge summary is available in Connected tools."
    count = len(data["credits"])
    return f"Demo bank statement retrieved. Credit entries: {count}. Match a payment using case evidence."


def connector_evidence(case_id: str, tools: list[str], previous: dict, values: dict, at: str) -> tuple[dict, list]:
    """Refresh approved fixtures, keeping their results distinct from the submitted claim."""
    prior = previous.get("evidence", {}) if previous.get("case_id") == case_id else {}
    prior_notes = {n["id"] for n in values.get("notifications", [])}
    evidence, notices = {}, []
    for tool, label in LABELS.items():
        if tool not in tools or (tool == "read_claim" and (values.get("submission") or {}).get("claim_id")):
            continue
        try:
            text = summary(tool, connector.read_fixture(case_id, tool))
        except connector.ConnectorError as exc:
            if exc.status in (401, 403):
                continue
            text = "The demo provider could not be read. Try refreshing its tools."
        evidence[tool] = text
        if prior.get(tool) != text:
            token = hashlib.sha256(f"{case_id}:{tool}:{text}".encode()).hexdigest()[:24]
            if f"provider-{token}" not in prior_notes:
                notices.append({"id": f"provider-{token}", "at": at, "kind": "update",
                                "text": f"{label}: {text}", "read": False})
    return evidence, notices


def authorized_evidence(state: dict, thread_id: str | None) -> dict:
    """Withhold previously read observations after revocation, expiry or gateway failure."""
    workspace = state.get("workspace_connectors") or {}
    if not thread_id or not workspace.get("evidence"):
        return {}
    try:
        tools = connector.connected_tools(workspace["case_id"], thread_id)
    except connector.ConnectorError:
        return {}
    return {tool: value for tool, value in workspace["evidence"].items() if tool in tools}


def email_updates(values: dict) -> None:
    """Mirror recent case updates to the opted-in demo inbox, with stable delivery IDs."""
    workspace = values.get("workspace_connectors") or {}
    if "case_email" not in workspace.get("tools", []):
        return
    notes = [n for n in values.get("notifications", [])
             if n["kind"] in ("update", "reminder") and not n.get("resolved")]
    if not notes:
        return
    batch = [{"id": hashlib.sha256(n["id"].encode()).hexdigest(), "at": n["at"], "kind": n["kind"]}
             for n in sorted(notes, key=lambda item: item["at"], reverse=True)[:50]]
    try:
        connector.deliver_notices(workspace["case_id"], batch)
    except connector.ConnectorError:
        # Email is secondary; the saved chat and case notifications remain the record.
        return
