"""Generate graphs G2 to G5: an editable Excalidraw source and an SVG export from one layout each.

G1 (product context) is drawn by hand in Excalidraw and is not generated here.
Run from the repository root:  python docs/diagrams/make_graphs.py
Outputs: docs/diagrams/src/gN-*.excalidraw (open in excalidraw.com to edit) and docs/diagrams/export/gN-*.svg.
Edits made by hand in Excalidraw are overwritten on the next run, so change the layout here first.
"""

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COLOURS = {
    "model": "#d0ebff",   # a model call
    "det": "#e9ecef",     # deterministic Python
    "human": "#ffe8cc",   # pause for a person
    "tool": "#d3f9d8",    # tools and confirmed outcomes
    "new": "#c3fae8",     # changed in this version
    "ext": "#fff3bf",     # API, external systems
    "warn": "#ffe3e3",    # failure or blocked state
    "store": "#f3d9fa",   # stored data
    "none": "#ffffff",
}
INK, MUTED = "#1e1e1e", "#495057"


class Diagram:
    """Collects boxes, arrows and text once and writes both the Excalidraw scene and the SVG."""

    def __init__(self, name: str, width: int, height: int):
        """Start an empty diagram.

        Args:
            name: File stem, for example "g2-lifecycle-and-state".
            width, height: SVG canvas size in pixels.
        """
        self.name, self.width, self.height = name, width, height
        self.elements: list[dict] = []
        self.svg: list[str] = []
        self.seq = 0

    def _base(self, **fields) -> dict:
        """Common Excalidraw element fields with a fresh id and seed."""
        self.seq += 1
        return {"id": f"e{self.seq}", "strokeColor": INK, "backgroundColor": "transparent", "fillStyle": "solid",
                "strokeWidth": 2, "roughness": 0, "opacity": 100, "seed": self.seq, "version": 1,
                "versionNonce": self.seq, "isDeleted": False, "angle": 0, "strokeStyle": "solid", "groupIds": [],
                "boundElements": [], "locked": False, **fields}

    def text(self, x: float, y: float, content: str, size: int = 13, anchor: str = "start", color: str = INK,
             bold: bool = False, width: float = 300, backing: bool = False) -> None:
        """Place text; y is the first baseline. anchor 'middle' centres each line on x.

        backing: draw a white box behind it so a label stays readable over lines.
        """
        lines = content.split("\n")
        if backing:
            w = max(len(line) for line in lines) * size * 0.56 + 6
            left = x - w / 2 if anchor == "middle" else x - 3
            self.svg.append(f'<rect x="{left:.0f}" y="{y - size:.0f}" width="{w:.0f}" '
                            f'height="{len(lines) * size * 1.25:.0f}" fill="#ffffff" opacity="0.92"/>')
        self.elements.append(self._base(
            type="text", x=x if anchor == "start" else x - width / 2, y=y - size, width=width,
            height=len(lines) * size * 1.25, text=content, originalText=content, fontSize=size, fontFamily=2,
            textAlign="left" if anchor == "start" else "center", verticalAlign="top", containerId=None,
            lineHeight=1.25, strokeColor=color, strokeWidth=1))
        weight = ' font-weight="bold"' if bold else ""
        for i, line in enumerate(lines):
            self.svg.append(f'<text x="{x}" y="{y + i * size * 1.25:.1f}" text-anchor="{anchor}" '
                            f'font-family="Segoe UI, Arial, sans-serif" font-size="{size}" fill="{color}"{weight}>'
                            f'{html.escape(line)}</text>')

    def box(self, x: float, y: float, w: float, h: float, content: str, kind: str = "det", size: int = 12,
            dashed: bool = False, rounded: bool = True) -> tuple[float, float, float, float]:
        """A filled box with centred text. Returns (x, y, w, h) for arrow placement."""
        fill = COLOURS[kind]
        self.elements.append(self._base(type="rectangle", x=x, y=y, width=w, height=h, backgroundColor=fill,
                                        roundness={"type": 3} if rounded else None,
                                        strokeStyle="dashed" if dashed else "solid"))
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{10 if rounded else 0}" fill="{fill}" '
                        f'stroke="{INK}" stroke-width="2"{dash}/>')
        lines = content.count("\n") + 1
        first = y + h / 2 - (lines - 1) * size * 1.25 / 2 + size * 0.35
        self.text(x + w / 2, first, content, size, "middle", width=w - 8)
        return x, y, w, h

    def frame(self, x: float, y: float, w: float, h: float, title: str = "", color: str = "#868e96",
              dashed: bool = True) -> None:
        """An unfilled boundary (lane, trust boundary or panel) with an optional title inside the top edge."""
        self.elements.append(self._base(type="rectangle", x=x, y=y, width=w, height=h, strokeColor=color,
                                        strokeWidth=1, roundness=None,
                                        strokeStyle="dashed" if dashed else "solid"))
        dash = ' stroke-dasharray="8 5"' if dashed else ""
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{color}" '
                        f'stroke-width="1.5"{dash}/>')
        if title:
            self.text(x + 10, y + 18, title, 13, color=color, bold=True, width=w - 20)

    def arrow(self, points: list[tuple[float, float]], label: str = "", at: tuple[float, float] | None = None,
              dashed: bool = False, color: str = INK, head: bool = True) -> None:
        """A polyline arrow ending at the last point (head=False: a plain line), with an optional label.

        The label sits at `at` (centred) or, by default, just above the middle of the longest segment.
        """
        x0, y0 = points[0]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        self.elements.append(self._base(
            type="arrow", x=x0, y=y0, width=max(xs) - min(xs), height=max(ys) - min(ys),
            points=[[px - x0, py - y0] for px, py in points], endArrowhead="arrow" if head else None, startArrowhead=None,
            strokeColor=color, strokeStyle="dashed" if dashed else "solid"))
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        coords = " ".join(f"{px},{py}" for px, py in points)
        self.svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="1.8" '
                        f'{' marker-end="url(#ah)"' if head else ""}{dash}/>')
        if label:
            if at is None:
                segs = list(zip(points, points[1:]))
                (ax, ay), (bx, by) = max(segs, key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
                lines = label.count("\n") + 1
                at = ((ax + bx) / 2, (ay + by) / 2 - 6 - (lines - 1) * 14 if ay == by else (ay + by) / 2)
            self.text(at[0], at[1], label, 11, "middle", MUTED, width=180, backing=True)

    def save(self) -> None:
        """Write src/<name>.excalidraw and export/<name>.svg."""
        scene = {"type": "excalidraw", "version": 2, "source": "claimwise make_graphs.py",
                 "elements": self.elements, "appState": {"viewBackgroundColor": "#ffffff"}, "files": {}}
        (ROOT / "src" / f"{self.name}.excalidraw").write_text(json.dumps(scene, indent=1), encoding="utf-8")
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
                f'viewBox="0 0 {self.width} {self.height}"><defs><marker id="ah" markerWidth="10" markerHeight="8" '
                f'refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="{INK}"/></marker></defs>'
                f'<rect width="100%" height="100%" fill="#ffffff"/>')
        (ROOT / "export" / f"{self.name}.svg").write_text(head + "".join(self.svg) + "</svg>", encoding="utf-8")


def right(b):
    """Middle of a box's right edge."""
    return b[0] + b[2], b[1] + b[3] / 2


def left(b):
    """Middle of a box's left edge."""
    return b[0], b[1] + b[3] / 2


def top(b, dx: float = 0):
    """Point on a box's top edge, dx from the centre."""
    return b[0] + b[2] / 2 + dx, b[1]


def bottom(b, dx: float = 0):
    """Point on a box's bottom edge, dx from the centre."""
    return b[0] + b[2] / 2 + dx, b[1] + b[3]


def legend(d: Diagram, x: float, y: float, items: list[tuple[str, str]]) -> None:
    """A row of colour swatches with their meaning."""
    for kind, meaning in items:
        d.box(x, y - 12, 18, 16, "", kind, rounded=False)
        d.text(x + 24, y, meaning, 12, color=MUTED, width=len(meaning) * 7)
        x += 24 + len(meaning) * 6.6 + 22


def panel(d: Diagram, x: float, y: float, w: float, h: float, title: str, lines: list[str]) -> None:
    """A titled notes panel."""
    d.frame(x, y, w, h, title, dashed=False)
    d.text(x + 12, y + 42, "\n".join(lines), 12, width=w - 24)


# ---------------------------------------------------------------- G2
def g2() -> None:
    """G2 lifecycle and state: onboarding, claim stage, write attempts, dispute; pauses and reopening."""
    d = Diagram("g2-lifecycle-and-state", 1880, 1280)
    d.text(30, 34, "G2  Lifecycle and state graph (BUILT, verified live 2026-11-06, session 037)", 20, bold=True,
           width=1400)
    d.text(30, 58, "Four state machines of one claim thread. Stage and payment status are recomputed from evidence "
           "every turn (C1, P1); nothing is marked done by hand. Function ids match G3.", 13, color=MUTED, width=1600)
    legend(d, 30, 86, [("det", "state (deterministic)"), ("human", "pause: a person must answer"),
                       ("tool", "confirmed outcome"), ("warn", "failed, blocked or needs attention"),
                       ("model", "read by the model")])

    # Lane A: onboarding (O1 to O3)
    d.frame(20, 110, 1840, 175, "A  Onboarding (O1 parse, O2 check, O3 confirm)")
    y, h = 160, 84
    a = [d.box(40, y, 180, h, "No documents\n(thread id created\nin the browser)"),
         d.box(260, y, 190, h, "Document uploaded\nstatus: uploaded\n(same bytes twice -> 409)"),
         d.box(490, y, 190, h, "O1 read by the model\nparsed | failed | rejected\n(rejected file deleted)", "model"),
         d.box(720, y, 210, h, "Policy facts pending\nPAUSE O3: confirm or correct\n(bad value -> 422)", "human"),
         d.box(970, y, 190, h, "Policy confirmed\n(corrected_fields kept;\nrejected: not this patient)"),
         d.box(1200, y, 200, h, "Role recorded (T1)\nself, or caregiver +\nauthority proof"),
         d.box(1440, y, 180, h, "Claim type chosen\n(button, no model;\nfixed after submission)"),
         d.box(1660, y, 180, h, "Onboarding complete\nclaim work starts", "tool")]
    for p, q in zip(a, a[1:]):
        d.arrow([right(p), left(q)])
    d.arrow([bottom(a[2], -40), (bottom(a[2], -40)[0], 268), (bottom(a[1], 40)[0], 268), bottom(a[1], 40)],
            "failed: upload again", dashed=True)

    # Lane B: claim stage (C1 and P1)
    d.frame(20, 300, 1840, 300, "B  Claim stage (C1 review_claim, P1 verify_payment): derived from documents and "
            "user-stated facts")
    y = 350
    b = {"prep": d.box(40, y, 170, 80, "preparing\n(checklist, issues,\nblockers)"),
         "appr": d.box(260, y, 190, 80, "approved_to_submit\n(approval hash =\ncurrent pack hash)", "human"),
         "sub": d.box(500, y, 200, 80, "submitted\nconnector claim id, or the\nuser's date (manual)", "tool"),
         "query": d.box(750, y, 190, 80, "query_raised\n(items, already sent?,\nanswer due date)", "warn"),
         "dec": d.box(990, y, 200, 80, "decided\napproved | partial | rejected\n(deductions, clauses)"),
         "rep": d.box(1240, y, 200, 80, "payment_reported\n(or top_up_due after a\nrevised decision)"),
         "ver": d.box(1500, y, 170, 80, "payment_verified\n(bank credit matches\nUTR or amount)", "tool"),
         "mis": d.box(1500, 490, 170, 80, "payment_mismatch\n(short or missing\ncredit)", "warn")}
    d.arrow([right(b["prep"]), left(b["appr"])], "approve pack")
    d.arrow([bottom(b["appr"]), (bottom(b["appr"])[0], 470), (bottom(b["prep"])[0], 470), bottom(b["prep"])],
            "pack changed: approval invalidated", dashed=True)
    d.arrow([right(b["appr"]), left(b["sub"])], "confirmed")
    d.arrow([(right(b["sub"])[0], 375), (left(b["query"])[0], 375)], "query")
    d.arrow([(left(b["query"])[0], 410), (right(b["sub"])[0], 410)], "answered", at=(725, 428))
    d.arrow([top(b["sub"]), (top(b["sub"])[0], 336), (top(b["dec"])[0], 336), top(b["dec"])], "decision letter")
    d.arrow([right(b["query"]), left(b["dec"])], "decision")
    d.arrow([right(b["dec"]), left(b["rep"])], "settlement")
    d.arrow([right(b["rep"]), left(b["ver"])], "matches")
    d.arrow([bottom(b["rep"]), (bottom(b["rep"])[0], 530), left(b["mis"])], "short or none")
    d.arrow([top(b["mis"], 40), bottom(b["ver"], 40)], "new statement", at=(1590, 470))
    d.arrow([bottom(b["dec"], -40), (bottom(b["dec"], -40)[0], 575), (bottom(b["prep"], 30)[0], 575),
             bottom(b["prep"], 30)], "balance claim on the 2nd policy: round 2, first round archived and enclosed",
            dashed=True)
    d.text(1690, 370, "rejected:\nnone_due\n(no payment\nexpected)", 11, color=MUTED, width=150)

    # Lane C: consequential writes
    d.frame(20, 615, 1840, 250, "C  Every write to the insurer: proposed -> approved -> attempted -> confirmed "
            "(submission, query reply; letters stop at approved)")
    y = 665
    c = {"prop": d.box(40, y, 190, 80, "Proposed\npack or letter drafted,\ncontent hash computed"),
         "appr": d.box(280, y, 200, 80, "Approved\nPAUSE approve card:\nuser OKs this exact hash", "human"),
         "att": d.box(540, y, 230, 80, "Attempted\nlook up client_reference first,\nthen send with the same key"),
         "conf": d.box(840, y, 210, 80, "Confirmed\npayer claim id read back\n(stage: submitted)", "tool"),
         "unc": d.box(300, 775, 250, 70, "timeout / 5xx: Unconfirmed\nanswer lost, never resent blind;\nM1 lookup confirms it later", "warn"),
         "ref": d.box(580, 775, 230, 70, "422: Refused\npayer reason shown,\nno automatic retry", "warn"),
         "exp": d.box(840, 775, 250, 70, "401/403: Connection expired\nconsent removed: reconnect,\nthen retry", "warn"),
         "man": d.box(1110, y, 230, 80, "Recorded by the user\nmanual route: date required,\nclaim number optional"),
         "blk": d.box(1400, y, 230, 80, "Blocked before any write:\nauthority withdrawn, expired\nor scope too narrow", "warn")}
    d.arrow([right(c["prop"]), left(c["appr"])], "approve")
    d.arrow([bottom(c["appr"], -60), (bottom(c["appr"], -60)[0], 760), (bottom(c["prop"])[0], 760), bottom(c["prop"])],
            "declined", at=(230, 772), dashed=True)
    d.arrow([right(c["appr"]), left(c["att"])], "submit / send")
    d.arrow([top(c["appr"]), (top(c["appr"])[0], 652), (top(c["man"])[0], 652), top(c["man"])],
            "or the user submits it outside Claimwise", at=(1000, 647), dashed=True)
    d.arrow([right(c["att"]), left(c["conf"])], "200 or found")
    d.arrow([bottom(c["att"], -60), (bottom(c["att"], -60)[0], 760), (top(c["unc"])[0], 760), top(c["unc"])])
    d.arrow([bottom(c["att"], 40), (bottom(c["att"], 40)[0], 760), (top(c["ref"])[0], 760), top(c["ref"])])
    d.arrow([bottom(c["att"], 80), (bottom(c["att"], 80)[0], 755), (top(c["exp"])[0], 755), top(c["exp"])])

    # Lane D: dispute
    d.frame(20, 880, 1840, 160, "D  Dispute (grievance.dispute_view): only when a decision is disputable")
    y = 930
    k = [d.box(40, y, 170, 80, "open\ndisputable decision\n(deduction, rejection)", "warn"),
         d.box(250, y, 190, 80, "grievance_approved\nPAUSE: approve letter\nbuilt from decision facts", "human"),
         d.box(480, y, 180, 80, "grievance_filed\ndate (+ reference);\n14-day reminder"),
         d.box(700, y, 200, 80, "Ombudsman eligible?\nreply rejects, or 30 days\nwith no reply; amount cap"),
         d.box(940, y, 190, 80, "ombudsman_approved\nPAUSE: approve\ncomplaint", "human"),
         d.box(1170, y, 170, 80, "ombudsman_filed\ndate (+ reference)"),
         d.box(1380, y, 210, 80, "revised\nnew decision letter: B goes back\nto decided; payment rechecked", "tool")]
    for p, q in zip(k, k[1:]):
        d.arrow([right(p), left(q)])
    d.arrow([bottom(k[2]), (bottom(k[2])[0], 1030), (bottom(k[6], -40)[0], 1030), bottom(k[6], -40)],
            "insurer revises after the grievance", dashed=True)

    # Panels
    panel(d, 20, 1060, 600, 205, "Interruption and resume", [
        "A pause (O3 confirm policy, approve pack, approve letter) is a LangGraph",
        "interrupt saved with the card in the checkpoint (Neon Postgres).",
        "POST /api/resume answers it. Any other turn or button first gets 409",
        "'Answer the card on screen first.'",
        "Closing the browser or restarting the server keeps the pause: reopening the",
        "thread shows the same card (V-34).",
        "No process waits for the insurer or the bank. M1 reads the connector each",
        "time the thread is opened, and a signed webhook triggers the same refresh.",
        "One thread never runs twice at once (per-thread lock in the API).",
    ])
    panel(d, 640, 1060, 600, 205, "What invalidates what", [
        "New or replaced document, policy choice or claim type: the pack hash",
        "changes, so the approval is stale (approval_invalidated), stage = preparing.",
        "Withdrawn or expired authority: approval cleared, every write blocked.",
        "Correcting a policy fact: O2 and C1 recompute everything downstream.",
        "A second file of the same type: version choice pending (replace or keep)",
        "blocks the pack until the user answers.",
        "After submission the claim type is fixed (409) and the pack is not resent",
        "(same hash = 'already submitted').",
    ])
    panel(d, 1260, 1060, 600, 205, "Legitimate reopening (not a restart)", [
        "Query answered: back to submitted; a new query: query_raised again.",
        "Only documents held before the query count as 'already sent'.",
        "Revised decision: decided again; payments made before it become",
        "a top-up due, not a short payment.",
        "Balance claim: a new round on the other policy; earlier letters archived.",
        "Reminders that are no longer due are kept, marked resolved.",
        "Connection expired: reconnect on the connector page; the claim and",
        "its history stay.",
    ])
    d.save()


# ---------------------------------------------------------------- G3
def g3() -> None:
    """G3 function execution: the LangGraph nodes, edges, pauses and the API that drives them (v0.8)."""
    d = Diagram("g3-agent-graph", 1840, 830)
    d.text(20, 32, "G3  Agent graph v0.8 (BUILT, verified live 2026-11-06, session 037)", 20, bold=True, width=1500)
    d.text(20, 56, "Every turn: START -> M1 -> O1 -> O2 -> C1 -> (P1) -> turn route. Button -> X1 -> C1 -> END. "
           "Typed text -> I1 -> A1 or R1. Uploads and tool results -> A1.", 13, color=MUTED, width=1700)
    legend(d, 20, 84, [("model", "model call"), ("det", "deterministic Python"), ("new", "changed in v0.8"),
                       ("human", "pause for the user"), ("tool", "tools"), ("ext", "API and external")])
    n = {"start": d.box(30, 160, 80, 50, "START"),
         "m1": d.box(140, 140, 190, 90, "M1 sync_connector  v0.8\nread submitted claim; reminders\n"
                     "(resolve when no longer due)", "new"),
         "gw": d.box(140, 250, 190, 60, "Connector gateway (8101)\n-> payer (8100)", "ext"),
         "o1": d.box(360, 140, 200, 90, "O1 parse_new_documents\nmodel reads the file; a 2nd\n"
                     "file of a type -> version choice", "model"),
         "o2": d.box(590, 140, 180, 90, "O2 check_onboarding\nwhat is missing, incl.\ncaregiver authority"),
         "o3": d.box(590, 330, 180, 90, "O3 confirm_facts\nPAUSE: user confirms\nor corrects policy facts", "human"),
         "c1": d.box(800, 140, 200, 90, "C1 review_claim  v0.8\nchecks, stage, blocks; a\n"
                     "later upload answers a query", "new"),
         "p1": d.box(1040, 140, 190, 90, "P1 verify_payment  v0.8\nsettlement vs bank credit;\n"
                     "top-up after revision", "new"),
         "route": d.box(1270, 140, 170, 90, "turn route\nroute_turn"),
         "a1": d.box(1490, 140, 190, 90, "A1 agent\nanswers, asks for the next\nitem, ends with a next step",
                     "model"),
         "end": d.box(1730, 160, 80, 50, "END"),
         "x1": d.box(1010, 330, 220, 150, "X1 run_action  v0.8\nbuttons: pack, submit, record,\nversions, policy "
                     "choice, balance\nclaim, grievance, Ombudsman,\nquery reply (send or dated)\n"
                     "PAUSE: approve pack or letter", "new"),
         "i1": d.box(1270, 330, 170, 80, "I1 classify_intent\nstructured: claim\nor off topic", "model"),
         "r1": d.box(1270, 460, 170, 60, "R1 reply_off_topic\nfixed text, no change"),
         "t1": d.box(1480, 330, 220, 100, "T1 tools\nclaim_deadline, record_role,\nupdate_claim, "
                     "prepare_submission\n(PAUSE: approve pack)", "tool"),
         "api": d.box(30, 330, 360, 215, "API  v0.8\nPOST /api/documents (same file twice -> 409)\n"
                      "POST /api/chat (+ /stream), /api/resume\n/resume checks policy corrections (422)\n"
                      "POST /api/action -> button press (X1)\nPOST /api/claim-type (no model)\n"
                      "GET /api/thread/{id} -> refresh (M1..C1)\nGET /api/threads?ids= (own ids only)\n"
                      "POST /api/connection, /authority (+ /withdraw)\nGET /api/pack/{id} (+ /pdf, /eml)\n"
                      "POST /api/webhooks/mock (HMAC) -> refresh", "new", size=11)}
    d.arrow([right(n["start"]), left(n["m1"])])
    d.arrow([bottom(n["m1"]), top(n["gw"])], "")
    d.arrow([right(n["m1"]), left(n["o1"])])
    d.arrow([right(n["o1"]), left(n["o2"])], "docs")
    d.arrow([(650, 230), (650, 330)], "policy not\nconfirmed", at=(612, 270))
    d.arrow([(730, 330), (730, 230)], "answered", at=(757, 262))
    d.arrow([right(n["o2"]), left(n["c1"])], "ready")
    d.arrow([right(n["c1"]), left(n["p1"])], "decided\nor paid")
    d.arrow([(900, 140), (900, 112), (1355, 112), (1355, 140)], "no decision or payment yet", at=(1130, 106))
    d.arrow([right(n["p1"]), left(n["route"])])
    d.arrow([right(n["route"]), left(n["a1"])], "uploads, tool\nresults", at=(1465, 212))
    d.arrow([right(n["a1"]), left(n["end"])], "reply", dashed=True)
    d.arrow([(1420, 140), (1420, 96), (1770, 96), (1770, 160)], "reply already made (after X1 or a refresh)",
            at=(1600, 90), dashed=True)
    d.arrow([(1290, 230), (1290, 290), (1120, 290), (1120, 330)], "button press", at=(1205, 284))
    d.arrow([(1010, 405), (900, 405), (900, 230)], "refresh review", at=(955, 420))
    d.arrow([(1355, 230), (1355, 330)], "typed text", at=(1395, 290))
    d.arrow([(1440, 360), (1462, 360), (1462, 260), (1520, 260), (1520, 230)], "claim", at=(1490, 252))
    d.arrow([(1355, 410), (1355, 460)], "off topic", at=(1392, 440))
    d.arrow([(1440, 490), (1790, 490), (1790, 210)], "fixed reply", at=(1700, 484), dashed=True)
    d.arrow([(1620, 230), (1620, 330)], "tool call", at=(1655, 290))
    d.arrow([(1590, 430), (1590, 580), (790, 580), (790, 215), (770, 215)], "state update / tool result: recheck from O2",
            at=(1130, 574))
    d.arrow([(390, 375), (590, 375)], "resume")
    panel(d, 20, 610, 520, 205, "STATE (checkpoint per thread_id)", [
        "messages; documents [{id, doc_type, status, facts, source,",
        "  version, uploaded_at}]; policies; user_role; onboarding",
        "claim_info {claim_type, submitted_on, claim_number, round}",
        "submission_approval {hash}  (stale when the pack changes)",
        "connection {case_id, status}  (case id never leaves the server)",
        "submission {route, status, claim_id, client_reference}",
        "notifications [{id, kind, read, resolved}]; requested_action",
        "authority; audit; dispute; claims_history",
        "Derived each turn: claim (C1) + claim.payment (P1)",
    ])
    panel(d, 560, 610, 520, 205, "C1 / P1 CHECKS (no model)", [
        "required documents; names and dates agree; policy period, totals",
        "query: item already sent (only documents held before the query)",
        "decision: per-line deductions, clause not cited",
        "P1: bank credit by UTR or amount; short or missing payment;",
        "  a revised decision after payment -> top_up_due",
        "late or overdue flags; reminders (grievance 14 days, authority",
        "  expiry); stale reminders resolved",
        "blocks: version choice pending, 2+ covering policies and none",
        "  chosen, authority withdrawn, expired or too narrow",
    ])
    panel(d, 1100, 610, 720, 205, "NEW IN v0.8 (session 037, found by the live end-to-end run)", [
        "X1: send the documents an insurer query asked for through the connector",
        "  (PAUSE approve letter, then gateway POST .../claims/{id}/documents), or",
        "  record the date the user sent them (uploaded query letters)",
        "API: claim type saved by the buttons without the model; policy corrections",
        "  validated before resume (422); thread list only for the caller's ids",
        "P1: top-up due after a revised decision instead of a false short payment",
        "M1: reminders that are no longer due are marked resolved",
        "Replies name the policy's TPA or insurer (no hard-coded provider)",
        "Observability: every node, model and tool call timed (TRACE_LOG) and traced",
        "  to LangSmith when LANGSMITH_API_KEY is set",
    ])
    d.save()


# ---------------------------------------------------------------- G4
LIFELINES = ["User", "Web app", "API (FastAPI)", "Agent graph", "Model\n(Gemini, Groq)", "Checkpoints\n(Neon)",
             "Connector\ngateway", "Payer (mock)"]


def g4() -> None:
    """G4 sequence and recovery: one full reimbursement journey, including an accepted-but-lost answer."""
    steps = [
        ("h", "1  Onboarding"),
        (0, 1, "upload policy PDF"), (1, 2, "POST /api/documents"), (2, 3, "run M1 -> O1"),
        (3, 4, "O1: read policy (structured fields)"), (4, 3, "insurer, number, members, period", "r"),
        (3, 5, "save checkpoint + PAUSE O3 confirm_policy"), (2, 1, "confirm card", "r"),
        (0, 1, "correct sum insured, confirm"), (1, 2, "POST /api/resume (422 if a value is invalid)"),
        (2, 3, "resume -> O2 -> C1 -> A1"), (3, 4, "A1: next step (+ tool record_role)"),
        (4, 3, "reply + tool call", "r"), (0, 1, "Reimbursement button"), (1, 2, "POST /api/claim-type (no model)"),
        ("h", "2  Evidence and approval"),
        (0, 1, "upload discharge summary and bill"), (1, 2, "POST /api/documents x2"),
        (2, 3, "O1 reads each; C1 checks names, dates, totals"), (0, 1, "Prepare claim pack"),
        (1, 2, "POST /api/action prepare_pack"), (2, 3, "X1: build pack, hash h1"),
        (3, 5, "PAUSE approve pack (card saved)"), (0, 1, "Approve"), (1, 2, "POST /api/resume approved"),
        (3, 5, "submission_approval = h1"),
        ("h", "3  Submission with the answer lost (fault: drop_response_after_commit)"),
        (0, 1, "Submit to insurer"), (1, 2, "POST /api/action submit"), (2, 3, "X1 submit_via_connector"),
        (3, 6, "find_claims(ref)"), (6, 7, "GET claims?client_reference=ref"), (7, 3, "none", "r"),
        (3, 6, "submit_claim(body, Idempotency-Key = ref)"), (6, 7, "POST /claims"),
        (7, 7, "commits CLM-1"), (7, 6, "500 after commit: answer lost", "r"), (6, 3, "unclear error", "r"),
        (3, 6, "recover: find_claims(ref)"), (6, 7, "GET claims?client_reference=ref"),
        (7, 3, "CLM-1 already held", "r"), (3, 5, "submission: submitted, claim_id CLM-1"),
        (2, 1, "Submitted. Settlement due in 15 days", "r"),
        ("h", "4  Waiting: an insurer query"),
        (7, 2, "signed webhook claim.query_raised (HMAC)"), (2, 3, "refresh: M1 read_claim"),
        (3, 6, "read_claim(CLM-1)"), (6, 3, "query: Discharge Card, lab report", "r"),
        (3, 5, "letter record (source connector) + notification"), (0, 1, "upload lab report"),
        (0, 1, "Send 2 documents to the insurer"), (2, 3, "X1 -> PAUSE approve query reply"),
        (0, 1, "Approve"), (3, 6, "answer_query(CLM-1, documents)"), (6, 7, "POST /claims/CLM-1/documents"),
        ("h", "5  Decision, payment and proof of money"),
        (7, 2, "webhooks: decided, paid"), (2, 3, "M1 read_claim"), (6, 3, "decision + payment UTR", "r"),
        (0, 1, "upload bank statement"), (3, 4, "O1: read statement credits"), (4, 3, "credits", "r"),
        (3, 3, "P1: UTR and amount match -> payment_verified"), (2, 1, "Paid in full, verified", "r"),
    ]
    xs = [90 + i * 190 for i in range(len(LIFELINES))]
    note_x = xs[-1] + 110
    gap, y0 = 25, 150
    height = y0 + sum(40 if s[0] == "h" else gap for s in steps) + 40
    d = Diagram("g4-sequence-and-recovery", note_x + 470, height)
    d.text(20, 32, "G4  Sequence and recovery graph: one reimbursement claim from upload to verified payment "
           "(BUILT, run live as J1 and J6, 2026-11-06)", 20, bold=True, width=1700)
    d.text(20, 56, "Solid = request, dashed = response. Every model call reads documents only; every write to the "
           "insurer follows an approval. Function ids match G3.", 13, color=MUTED, width=1700)
    for x, name in zip(xs, LIFELINES):
        kind = {"User": "human", "Model\n(Gemini, Groq)": "model", "Checkpoints\n(Neon)": "store",
                "Connector\ngateway": "ext", "Payer (mock)": "ext"}.get(name, "det")
        d.box(x - 75, 80, 150, 46, name, kind)
        d.arrow([(x, 126), (x, height - 20)], dashed=True, color="#adb5bd", head=False)
    y = y0
    for step in steps:
        if step[0] == "h":
            y += 12
            d.box(10, y - 14, xs[-1] + 90, 22, "", "none", rounded=False)
            d.text(18, y + 2, step[1], 13, bold=True, width=900)
            y += 28
            continue
        src, dst, label, *style = step
        if src == dst:
            d.arrow([(xs[src], y - 8), (xs[src] + 40, y - 8), (xs[src] + 40, y + 6), (xs[src] + 4, y + 6)])
            d.text(xs[src] + 48, y + 3, label, 11, color=MUTED, width=300)
        else:
            d.arrow([(xs[src], y), (xs[dst], y)], dashed=bool(style))
            d.text((xs[src] + xs[dst]) / 2, y - 5, label, 11, "middle", MUTED, width=300, backing=True)
        y += gap
    panel(d, note_x, 150, 450, 200, "Recovery: accepted but the answer was lost", [
        "The client reference is a hash of the thread and the",
        "approved pack. It is also the Idempotency-Key, so the",
        "payer returns the same claim for the same key.",
        "Before every send, and after any unclear failure, the",
        "payer is asked whether it already holds the reference.",
        "If that lookup fails too: status unconfirmed. Nothing",
        "is resent blind; M1 repeats the lookup on every open",
        "and adopts the claim when it appears.",
        "Verified live: one claim at the payer after a dropped",
        "answer and a double click (V-10, V-09, V-31).",
    ])
    panel(d, note_x, 370, 450, 180, "Other failure exits", [
        "Payer down (5xx, timeout): unconfirmed, reply says so.",
        "Refused (422 with a reason): shown, no retry.",
        "Consent removed or session ended (401/403):",
        "  connection expired; reconnect, then retry.",
        "Webhook with a bad signature: 401, no state change.",
        "Webhook lost: the next thread open runs M1 anyway.",
        "Model down or rate-limited: Groq fallback; a failed",
        "  parse leaves the document 'failed', upload again.",
        "Text inside letters is data, never instructions (J7).",
    ])
    panel(d, note_x, 570, 450, 130, "Long waits and resume", [
        "No worker waits on the insurer: state lives in the",
        "checkpoint, M1 reads the claim on open or webhook.",
        "Pauses (O3, approve pack, approve letter) survive a",
        "browser close or a server restart (V-34).",
        "Reminders are dated and deterministic (no duplicates);",
        "they resolve when the condition passes.",
    ])
    d.save()


# ---------------------------------------------------------------- G5
def g5() -> None:
    """G5 data and context: stores, ownership, provenance, versions, what the model sees, retention."""
    d = Diagram("g5-data-and-context", 1860, 1100)
    d.text(20, 32, "G5  Data and context graph (BUILT prototype, synthetic data only, 2026-11-06)", 20, bold=True,
           width=1500)
    d.text(20, 56, "Where each fact comes from, who owns it, where it is stored, what the model sees, and how a "
           "correction or a new version flows downstream.", 13, color=MUTED, width=1700)
    legend(d, 20, 84, [("ext", "outside Claimwise"), ("store", "stored"), ("det", "derived each turn"),
                       ("model", "model input or output"), ("human", "user decision"), ("warn", "never shared")])

    d.frame(20, 110, 300, 700, "Sources (untrusted input)")
    src = {"up": d.box(40, 150, 260, 70, "Uploads: PDF, PNG, JPEG\n(type and size checked;\nsha256: same bytes -> 409)",
                       "ext"),
           "chat": d.box(40, 245, 260, 60, "Typed messages\n(I1 checks claim or off topic)", "ext"),
           "btn": d.box(40, 330, 260, 60, "Button presses and forms\n(fixed ids, validated values)", "human"),
           "conn": d.box(40, 415, 260, 80, "Connector records\npayer queries, decision, payments\n(source: connector)",
                         "ext"),
           "hook": d.box(40, 520, 260, 70, "Signed webhooks\nHMAC checked; only a trigger,\nthe data is re-read", "ext"),
           "rules": d.box(40, 615, 260, 70, "Rule tables in code\nTATs, required documents,\nOmbudsman limits", "det")}
    d.frame(350, 110, 980, 700, "Trust boundary: Claimwise server (FastAPI + LangGraph)", color="#1971c2",
            dashed=False)
    s = {"files": d.box(380, 150, 280, 80, "Upload store (UPLOAD_DIR)\nfile bytes by server id;\n"
                        "rejected files deleted", "store"),
         "o1": d.box(380, 280, 280, 90, "O1 extraction (model)\nfile -> structured facts + doc_type\n"
                     "text in a file is data, never\nan instruction", "model"),
         "ck": d.box(700, 150, 600, 230, "Checkpoint store (Neon Postgres, one thread_id per claim)\n\n"
                     "documents: facts, status, source, version, version_of,\n  uploaded_at, sha256\n"
                     "policies: facts + status + corrected_fields (user-owned)\n"
                     "user_role, authority (scope, expiry, status), audit\n"
                     "claim_info (claim type, dates, round), connection {case_id}\n"
                     "submission_approval {hash}, submission {client_reference}\n"
                     "dispute (approved letter hashes, filing dates),\n"
                     "notifications, claims_history, messages", "store", size=12),
         "derived": d.box(380, 420, 400, 110, "Derived every turn, never edited (C1, P1)\nchecklist, issues, stage, "
                          "pack + hash,\nquery (already sent?), decision lines,\npayment status, dispute view"),
         "ctx": d.box(820, 420, 480, 110, "Model context (A1 prompt)\nrules + onboarding context + claim context +\n"
                      "buttons on screen + conversation\n(policy facts, stage, issues, amounts)", "model"),
         "never": d.box(820, 570, 480, 90, "Never sent to the model or the browser\nfile paths, connector case id, "
                        "server key,\nproof file contents, webhook secret", "warn"),
         "pack": d.box(380, 570, 400, 90, "Outputs the user approves\nclaim pack (PDF, .eml), grievance and Ombudsman\n"
                       "letters, query reply: bound to a content hash", "human"),
         "obs": d.box(380, 700, 920, 80, "Observability: TRACE_LOG (local JSONL: node, model, tool, ms, tokens, "
                      "status) and LangSmith\nwhen LANGSMITH_API_KEY is set (prompts and outputs: synthetic data only "
                      "until a privacy review)", "ext")}
    d.frame(1360, 110, 480, 700, "Outside Claimwise")
    out = {"browser": d.box(1380, 150, 440, 70, "Browser localStorage\nthread ids only (the only key to a claim;\n"
                            "no login yet: TBD)", "ext"),
           "gw": d.box(1380, 250, 440, 90, "Connector gateway\ncase grant + per-tool consent (submit, read,\n"
                       "answer query); server bearer key; consent can be\nremoved at any time -> 401/403", "ext"),
           "payer": d.box(1380, 370, 440, 80, "Payer (mock)\nclaims by client_reference (idempotent),\n"
                          "queries, decisions, payments, letters", "ext"),
           "llm": d.box(1380, 480, 440, 70, "Model providers\nGemini (primary), Groq (fallback)", "model"),
           "ls": d.box(1380, 580, 440, 70, "LangSmith (project claimwise)\nrun tree per turn: route, thread, "
                       "latency", "ext")}
    d.arrow([right(src["up"]), left(s["files"])], "bytes")
    d.arrow([bottom(s["files"]), top(s["o1"])], "file")
    d.arrow([right(s["o1"]), (690, 325), (690, 300), (700, 300)], "facts")
    for key, y in (("chat", 275), ("btn", 360), ("conn", 455)):
        d.arrow([right(src[key]), (335, y), (335, 398), (710, 398), (710, 380)], "")
    d.text(520, 394, "messages, choices, connector records", 11, "middle", MUTED, width=260, backing=True)
    d.arrow([(760, 380), (760, 420)], "state", at=(790, 408))
    d.arrow([(1050, 380), (1050, 420)], "state", at=(1080, 408))
    d.arrow([right(s["derived"]), left(s["ctx"])], "")
    d.arrow([bottom(s["derived"]), top(s["pack"])], "pack")
    d.arrow([(1300, 200), (1340, 200), (1340, 185), (1380, 185)], "thread id")
    d.arrow([(1380, 275), (1300, 275)], "records", at=(1340, 268))
    d.arrow([(1300, 325), (1380, 325)], "submit,\nanswer", at=(1340, 345))
    d.arrow([bottom(out["gw"]), top(out["payer"])], "consented calls only", at=(1700, 360))
    d.arrow([right(s["ctx"]), (1340, 475), (1340, 515), left(out["llm"])], "prompt")
    d.arrow([right(s["obs"]), (1350, 740), (1350, 615), left(out["ls"])], "traces")

    panel(d, 20, 830, 590, 255, "Ownership and provenance", [
        "Every document keeps its source: an upload (default) or the",
        "connector (source: connector, seen time in uploaded_at).",
        "Policy facts: read by the model, owned by the user once confirmed;",
        "  corrected_fields records which ones the user changed.",
        "Role, claim type, dates and references: stated by the user",
        "  (buttons or forms), validated at the API.",
        "Authority: recorded by the caregiver with proof; the patient is the",
        "  grantor; Claimwise records it, it cannot grant it.",
        "Stage, issues, payment and dispute status: derived, never stored",
        "  as a user decision, so they cannot drift from the evidence.",
        "Audit log: who did what and when (every button action, claim type,",
        "  authority recorded or withdrawn).",
        "Connector case id and server key stay on the server.",
    ])
    panel(d, 630, 830, 590, 255, "Versions, corrections and approval invalidation", [
        "A 2nd file of the same type: version_of set, choice pending;",
        "  replace -> old one superseded; keep -> both stay in the pack.",
        "A balance claim archives the first round's insurer letters and",
        "  encloses them; history keeps the first decision.",
        "Correction flow: user corrects a policy fact -> policies updated ->",
        "  O2 recheck -> C1 recompute -> pack hash changes -> approval",
        "  stale (approval_invalidated) -> user approves again.",
        "Letters: an approved grievance or Ombudsman letter is bound to",
        "  its hash; a revised decision starts a new dispute view.",
        "Withdrawn authority clears the pack approval and blocks writes.",
        "Query 'already sent' counts only documents held before the query.",
    ])
    panel(d, 1240, 830, 600, 255, "Retention and deletion (prototype status)", [
        "Built: rejected uploads are deleted at once; superseded and",
        "  archived documents are kept as claim evidence.",
        "Built: the thread list only returns ids the browser already",
        "  holds; the server never lists every claim.",
        "Not built (TBD before real users): user login and tenancy,",
        "  deleting a thread and its files, a retention period for",
        "  checkpoints, uploads and traces, export of a user's data.",
        "LangSmith receives prompts and outputs: keep it to synthetic",
        "  data, or turn tracing off, until a privacy review approves it.",
        "Secrets (model keys, LangSmith key, connector key, webhook",
        "  secret) live in backend/.env, never in state or logs.",
    ])
    d.save()


if __name__ == "__main__":
    g2(), g3(), g4(), g5()
    print("wrote G2 to G5")
