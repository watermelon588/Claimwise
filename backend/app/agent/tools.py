"""Agent tools. Deterministic Python only: the model calls them, it never does the maths itself."""

from datetime import date, timedelta
from typing import Literal

from langchain_core.tools import tool

# IRDAI 2024 circular timers (RESEARCH_DOSSIER P-04, P-13, P-14, P-15). Current applicability not verified.
RULES: dict[str, list[tuple[int, str]]] = {
    "claim_submitted": [(15, "Insurer must settle a non-cashless claim (else interest at bank rate + 2%)")],
    "grievance_filed": [
        (14, "Insurer must resolve the grievance with reasons"),
        (30, "Ombudsman route opens if still unresolved or the reply is unacceptable"),
    ],
    "ombudsman_award": [(30, "Insurer must comply with the Ombudsman award")],
}


@tool
def claim_deadline(
    event: Literal["claim_submitted", "grievance_filed", "ombudsman_award"], event_date: date
) -> list[dict]:
    """Return the regulatory due dates that follow a claim event.

    Args:
        event: What happened: claim_submitted, grievance_filed or ombudsman_award.
        event_date: The date it happened (YYYY-MM-DD).
    Returns:
        One entry per rule with the due date, days allowed and what is due.
    """
    return [
        {"due_date": (event_date + timedelta(days=d)).isoformat(), "days": d, "rule": rule}
        for d, rule in RULES[event]
    ]


TOOLS = [claim_deadline]
