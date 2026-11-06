"""Date maths for claim_deadline. No LLM needed."""

from app.agent.tools import claim_deadline


def test_claim_deadline_dates():
    """Settlement is 15 days out; grievance gives 14-day reply and 30-day ombudsman dates."""
    [settle] = claim_deadline.invoke({"event": "claim_submitted", "event_date": "2026-11-01"})
    assert settle["due_date"] == "2026-11-16"
    reply, ombudsman = claim_deadline.invoke({"event": "grievance_filed", "event_date": "2026-12-25"})
    assert (reply["due_date"], ombudsman["due_date"]) == ("2027-01-08", "2027-01-24")
