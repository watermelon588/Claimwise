"""Payment verification (P1) rules and its place in the graph. No LLM key needed."""

from datetime import date

from app.agent.claim import review_claim
from app.agent.payment import check_payment, route_after_review, verify_payment
from tests.test_claim import BILL, SUMMARY, base_state, doc

DECISION = doc("dec", "insurer_letter", {"letter_kind": "decision", "letter_date": "2026-10-20", "outcome": "partially_approved",
                                        "claimed_amount": 50000, "approved_amount": 42000, "line_decisions": []})
SETTLED = doc("set", "insurer_letter", {"letter_kind": "settlement", "letter_date": "2026-10-22",
                                       "paid_amount": 42000, "utr": "SBIN 0042 1234", "paid_on": "2026-10-22"})
TODAY = date(2026, 10, 25)


def statement(*credits: dict, to: str = "2026-10-31") -> dict:
    """Bank statement document with the given credit lines."""
    return doc("bank", "bank_statement", {"statement_from": "2026-10-01", "statement_to": to, "credits": list(credits)})


def check(*docs: dict, **info) -> tuple[str, list[str], dict]:
    """Run C1 then the payment check; return (status, issue codes, payment)."""
    state = base_state(SUMMARY, BILL, *docs, claim_info={"claim_type": "reimbursement", "submitted_on": "2026-10-10", **info})
    state["claim"] = review_claim(state)["claim"]
    payment, issues = check_payment(state, TODAY)
    return payment["status"], [i["code"] for i in issues], payment


def test_settlement_letter_keeps_the_decision():
    """A settlement letter after the decision must not hide the decision (old read_decision bug)."""
    claim = review_claim(base_state(SUMMARY, BILL, DECISION, SETTLED))["claim"]
    assert claim["decision"]["approved"] == 42000 and claim["decision"]["letter_doc_id"] == "dec"


def test_verified_by_utr_inside_narration():
    """The UTR printed inside the narration (with spaces dropped) is enough to match."""
    status, codes, payment = check(DECISION, SETTLED, statement(
        {"date": "2026-10-23", "amount": 42000, "utr": None, "narration": "NEFT CR SBIN00421234 SURAKSHA GEN"}))
    assert (status, codes, payment["match"]) == ("verified", [], "utr")


def test_verified_by_amount_and_date_without_settlement_letter():
    """No settlement letter: the approved amount credited after the decision counts."""
    status, codes, payment = check(DECISION, statement({"date": "2026-10-28", "amount": 42000}))
    assert (status, codes, payment["match"]) == ("verified", [], "amount_and_date")
    # The same amount before the decision is not this payment.
    assert check(DECISION, statement({"date": "2026-10-05", "amount": 42000}))[1] == ["credit_not_found"]


def test_mismatches():
    """Short payment, a different credited amount, a missing credit and a duplicate are all flagged."""
    short = doc("set", "insurer_letter", {**SETTLED["facts"], "paid_amount": 40000})
    assert check(DECISION, short, statement({"date": "2026-10-22", "amount": 40000, "utr": "SBIN00421234"}))[:2] == ("mismatch", ["short_payment"])
    assert check(DECISION, SETTLED, statement({"date": "2026-10-22", "amount": 41000, "utr": "SBIN00421234"}))[:2] == ("mismatch", ["credit_amount_mismatch"])
    assert check(DECISION, SETTLED, statement({"date": "2026-10-22", "amount": 500}))[:2] == ("mismatch", ["credit_not_found"])
    twice = {"date": "2026-10-22", "amount": 42000, "utr": "SBIN00421234"}
    assert check(DECISION, SETTLED, statement(twice, twice))[:2] == ("mismatch", ["duplicate_credit"])


def test_missing_or_old_statement_and_timing():
    """No statement asks for one; an old statement asks for a newer one; late and overdue settlement are flagged."""
    assert check(DECISION, SETTLED)[:2] == ("reported", ["bank_statement_needed"])
    assert check(DECISION, SETTLED, statement(to="2026-10-15"))[:2] == ("reported", ["statement_too_old"])
    late = doc("set", "insurer_letter", {**SETTLED["facts"], "paid_on": "2026-10-30"})
    assert "late_settlement" in check(DECISION, late, submitted_on="2026-10-01")[1]
    assert check(DECISION, submitted_on="2026-10-01")[:2] == ("awaiting", ["settlement_overdue", "bank_statement_needed"])


def test_rejected_and_cashless():
    """A rejection has nothing to pay; cashless is paid to the hospital and shows the patient's share."""
    rejected = doc("dec", "insurer_letter", {"letter_kind": "decision", "outcome": "rejected", "clause": "3.1"})
    assert check(rejected)[:2] == ("none_due", [])
    status, codes, _ = check(DECISION, claim_type="cashless")
    assert (status, codes) == ("paid_to_hospital", ["cashless_patient_share"])


def test_route_and_stage():
    """C1 routes to P1 only once there is a decision or a settlement; P1 moves the stage on."""
    state = base_state(SUMMARY, BILL)
    state["claim"] = review_claim(state)["claim"]
    assert route_after_review(state) == "agent"
    state = base_state(SUMMARY, BILL, DECISION, SETTLED, statement({"date": "2026-10-22", "amount": 42000, "utr": "SBIN00421234"}))
    state["claim"] = review_claim(state)["claim"]
    assert route_after_review(state) == "verify_payment"
    claim = verify_payment(state)["claim"]
    assert claim["stage"] == "payment_verified" and claim["payment"]["credit"]["amount"] == 42000


def test_overlap_and_statement_period_gap():
    """Overlapping statements repeat one transfer; a gap triggers a targeted upload request."""
    credit = {"date": "2026-10-23", "amount": 42000, "utr": "SBIN00421234"}
    october = statement(credit)
    overlap = doc("nov", "bank_statement", {
        "statement_from": "2026-10-20", "statement_to": "2026-11-10", "credits": [credit],
    })
    assert check(DECISION, SETTLED, overlap, october)[:2] == ("verified", [])

    later = doc("nov", "bank_statement", {
        "statement_from": "2026-10-24", "statement_to": "2026-11-10", "credits": [],
    })
    assert check(DECISION, SETTLED, statement(to="2026-10-18"), later)[:2] == (
        "reported", ["bank_statement_needed"],
    )


def test_distinct_payment_cannot_reuse_an_earlier_credit():
    """Reserve a credit for its prior transfer, while a reissued notice can still cite that transfer."""
    bank = statement({"date": "2026-10-23", "amount": 42000, "utr": "SBIN00421234"})
    another = doc("another", "insurer_letter", {**SETTLED["facts"], "utr": None, "paid_on": "2026-10-23"})
    status, codes, payment = check(DECISION, SETTLED, another, bank)
    assert (status, codes, payment["credit"]) == ("mismatch", ["credit_not_found"], None)

    reissued = doc("reissued", "insurer_letter", {**SETTLED["facts"], "utr": "sbin00421234"})
    assert check(DECISION, SETTLED, reissued, bank)[:2] == ("verified", [])


def test_bank_follow_up_and_ambiguous_amounts():
    """No bank request before a decision; duplicate amount-only candidates need a reference."""
    assert check()[:2] == ("awaiting", [])
    bank = statement(
        {"date": "2026-10-23", "amount": 42000, "utr": "FIRST"},
        {"date": "2026-10-24", "amount": 42000, "utr": "SECOND"},
    )
    assert check(DECISION, bank)[:2] == ("mismatch", ["ambiguous_credit"])
    state = base_state(DECISION, SETTLED, bank)
    state["claim"] = review_claim(state)["claim"]
    _, issues = check_payment(state, TODAY)
    [issue] = [item for item in issues if item["code"] == "credit_not_found"]
    assert "complaint with the bank first" in issue["message"]
    assert "RBI Integrated Ombudsman Scheme" in issue["message"]
