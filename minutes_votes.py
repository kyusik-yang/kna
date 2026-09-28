"""
Parse and link recorded plenary votes from the minutes PDFs (17th-19th)
=======================================================================
Used by collect_minutes_votes.py. One minutes PDF (국회본회의 회의록) holds

  * in the body, every chair announcement of a vote result, '재석 N인 중
    찬성 N인, 반대 N인, 기권 N인으로서 ... 가결되었음을 선포합니다', and for
    an electronic (recorded) vote the marker '(찬반 의원 성명은 끝에 실음)'.
  * in the appendix, under 【전자투표 찬반 의원 성명】, one block per recorded
    vote: a ◯ title, the printed group counts 투표/찬성/반대/기권 의원(N인),
    the names under 찬성, 반대 and 기권, and sometimes a note in parentheses.

Text is read with PyMuPDF and NFKC-normalised, which also folds the CJK
compatibility ideographs in which some Hanja names are printed.

Events
------
One event per ◯ block of the appendix. A block with a second 투표 label under
the same title is a repeat of that vote (revote_seq 2, 3, ...), and '<1차 투표>'
and '<2차 투표>' go to appendix_note. A ◯ heading that ends in '의원(N인)'
(출석 의원 and similar) is a list, not a vote. vote_event_id is
'{age}_{CONFER_NUM}_{event_seq:03d}', event_seq counting the blocks of the
meeting in print order. meeting_date is the date of the minutes, and date is
the date of the vote, which differs only when a sitting runs past midnight
('(2월23일 24시 경과)', one 19th meeting).

Names are separated by two or more spaces. A name whose syllables are each
separated by one space ('문 희 상', some 17th minutes) is joined, and two
single syllables are joined when they make a member's name ('김  현').
Dropped and listed in dropped_lines: lines with digits (page furniture,
result tables) and lines of which fewer than half the name-like tokens are
members' names (prose printed after the last list). When the names still
outnumber the printed count, runs of two or more lines holding at most one
token are dropped as text interleaved from elsewhere on the page.

Chair counts
------------
Each event is aligned to a chair announcement of the same meeting
(chair_align): 'order' when the meeting has as many marked announcements as
events and every pair in print order has the same title. Otherwise 'title',
a one-to-one match on the title, then 'order_rest' for votes left over, or
'unaligned'. The appendix names are the member-level record. The chair's
counts are kept beside them (chair_present, chair_yes, chair_no,
chair_abstain, chair_result 가결/부결) with chair_counts_differ when any
count differs from the names. correction_note is true when the appendix
block carries a note giving the actual counts ('... 표결기 조작 지체. 실제
찬성 의원 N인 ...', also printed '실체', or '표결기 오작동'), and
correction_note_matches_names says whether the note's counts equal the names.
A chair announcement that cannot be read as counts (a misspoken '반대 191인,
반대 5인') leaves the chair columns null.

Bills
-----
Titles are compared after reading Hanja in Hangul, removing spaces,
brackets and punctuation, and folding the initial-sound law. A title '<bill>에
대한 수정안' is a vote on a floor amendment (vote_on 'amendment') and '<bill>에
대한 번안' a vote to reverse a decision (vote_on 'reversal'). Both are
linked to <bill>. Candidates are the bills of master_bills_{age} decided in
the plenary on the vote date (rgs_rsln_dt, proc_dt or nzpltgfqabtcpsmai
PROC_DT), then the bills pending on it (proposed on or before the date,
decided on or after it). bill_link records the method:
  exact_decided   one bill decided on the date with plenary_decided = 1 has the title
  exact_any       one bill decided on the date has the title
  exact_pending   one bill pending on the date has the title
  fuzzy           best similarity among bills decided on the date >= 0.85
  ambiguous_*     more than one bill has the title (not linked, bill_candidates)
  unlinked        no bill qualifies (petitions, procedural motions)
  no_bill_on_date nothing decided on the date and no pending bill has the title
vote_type is 'original' (a vote on the bill), 'amendment', 'reversal',
'revote' (revote_seq > 1) or 'other' (no bill_id).

Members
-------
A printed name is matched to members_{age} (member_match): a Hanja form to
the member with that member_name_hanja ('hanja'), a Hangul form to the one
member with that name ('name'), a spelling in ALIASES ('name_spelling').
For a name two members share (SAME_NAME) the rules below apply in order.
Nothing else is inferred: when no rule applies, member_id stays null.
  same_name_seated_alone  only one of the two held the seat on the vote date
                          (seat dates and their sources in SAME_NAME)
  same_name_event_hanja   one Hangul row in a vote that also prints exactly
                          one member of the pair in Hanja: the Hangul row is
                          the other member (no member votes twice)
  same_name_pair_same_vote  the Hangul name twice in one vote with the same
                          vote: one row per member
  unresolved_same_name    one Hangul row with no Hanja form of the pair in
                          the vote, or the name twice with different votes
  printed_on_two_lists    a unique name printed on two lists of one vote
  unmatched               a name that is no member's
The minutes print the Hanja form for either member of a pair: for 김선동 the
member seated later (金先東), for 이영애 the one seated first (李玲愛). The
Hanja form is therefore mapped through member_name_hanja, never through the
order of entry. Nor is a meeting-wide printing habit used, because it is
not stable within a meeting: meeting 35126 (18th, 2011-04-29) prints the
pair as 金先東 and 김선동 in 49 votes and as 김선동 twice in one, so a Hangul
row alone is not evidence of which member voted.

A name printed twice on the same list of one vote (27710, 17th: 원혜영) is
kept once and recorded in names_printed_twice.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

# ── same-name members ───────────────────────────────────────────────────
# Names that two members of an assembly share, with the dates each member
# held the seat: {mona_cd: (first date, first date no longer seated)}, None
# for the start or the end of the assembly. Both members are in
# members_{age}, and their Hanja forms come from member_name_hanja. The dates
# are those of the minutes. A later member counts from the meeting at which the
# oath was taken, which in every case below came before that meeting's votes.
SAME_NAME = {
    18: {
        "김선동": {
            "DTG4846A": (None, None),
            # 金先東, 전남 순천시: by-election of 2011-04-27 (appendix notice of
            # meeting 35126), sworn in at the start of meeting 35126 on
            # 2011-04-29 ('의원(손학규.김태호.김선동) 선서 및 인사').
            "ZC87486D": ("2011-04-29", None),
        },
        "이영애": {
            "8TG3670K": (None, None),
            # 李榮愛: '10월 4일자로 비례대표 의석을 승계한 이영애 의원', sworn in
            # at the start of meeting 35567 on 2011-10-10, the first plenary
            # after 2011-09-16. Her first committee post in nqbeopthavwwfbekw
            # is 2011-10-05, that of 8TG3670K 2008-07-15.
            "PU97362N": ("2011-10-10", None),
        },
    },
    19: {
        "권은희": {
            "PFM7673W": (None, None),
            # 權垠希, 광주 광산구을: by-election of 2014-07-30, sworn in at the
            # start of meeting 38621 on 2014-09-01 (printed 權垠希 in the list
            # of members sworn in). No plenary met in the 327th and 328th
            # sessions ('본회의는 사정에 의하여 개의되지 않았음').
            "YKW37422": ("2014-09-01", None),
        },
        "김영주": {
            "0W194007": (None, None),
            # 金永柱, 비례대표: '비례대표 국회의원 김영주 의원의 퇴직으로 궐원된
            # 의석' (appendix of meeting 37857), vacancy notified 2013-12-12. No
            # plenary met between 2013-12-10 and 2013-12-19.
            "E6S73230": (None, "2013-12-12"),
        },
        "이재영": {
            "URQ4401W": (None, None),
            # 李在暎, 경기 평택시을: '1월 16일, 대법원 확정판결에 따라 신장용
            # 의원, 이재영 의원, 현영희 의원, 이상 3인이 궐원' (meeting 38086,
            # 2014-02-03). The seat is the 평택 one, because its by-election
            # winner 유의동 ('경기 평택 출신') was sworn in at meeting 38621.
            "1XO42697": (None, "2014-01-16"),
        },
    },
}


def seated(period: tuple, date: str) -> bool:
    start, end = period
    return (start is None or date >= start) and (end is None or date < end)


# Printed spellings of a member's name that differ from members_{age}. Only
# the initial-sound-law spelling (두음법칙) of a surname, where the roster has
# the other spelling and no member has the printed one.
ALIASES = {
    17: {"유근찬": "류근찬"},
}

# ── text ────────────────────────────────────────────────────────────────

PAGE_HDR_RE = re.compile(
    r"^\s*(\d+\s+)?[제第]\s*\d+\s*[회回]\s*[-－–]\s*([제第]\s*\d+\s*[차次]|개회식|폐회식|開會式|閉會式)"
    r"\s*(\(\s*\d{4}\s*년\s*\d+\s*월\s*\d+\s*일\s*\))?(\s+\d+)?\s*$")
CIRCLE = "◯○"
LABEL_RE = re.compile(r"^\s*(투표|찬성|반대|기권)\s*의\s*원\s*\(\s*(\d+)\s*[인人]\s*\)\s*(.*)$")
REVOTE_RE = re.compile(r"^\s*[<〈＜《]\s*.{0,12}(투표|표결).{0,6}[>〉＞》]\s*$")
HANGUL_NAME = re.compile(r"^[가-힣]{2,4}$")
HANJA_NAME = re.compile(r"^[一-鿿]{2,4}$")
ROLLCALL_HEAD_RE = re.compile(r"^\s*【?\s*(전\s*자\s*투\s*표|電\s*子\s*投\s*票).{0,20}(성\s*명|姓\s*名)\s*】")
HEAD_RE = re.compile(r"(?:재[석적](?:의원)?|투표결과를말씀드리겠습니다\.?)(\d+)(?:인|명|분)?"
                     r"(?:중에서|중에|중|가운데에서|가운데서|가운데|[,，])")
CLAUSE_END_RE = re.compile(r"으로서|로서|그래서|따라서|그러므로|이므로|입니다|가결|부결|선포")
YES_RE = re.compile(r"찬성(?:도|은|이)?(?:또한|역시)?[이은]?[,，]?(\d+)(?:인|명|분)?|(\d+)(?:인|명)찬성")
NO_RE = re.compile(r"반대(?:가|는|도)?[,，]?(\d+)(?:인|명|분)?")
ABSTAIN_RE = re.compile(r"기권(?:이|은|도)?[,，]?(\d+)(?:인|명|분)?")
NIL_RE = re.compile(r"[,，]?(?:반대|기권)(?:가|는|이|은|도)?(?:없고|없으며|없이|없습니다\.?|없음)")
UNANIMOUS_RE = re.compile(
    r"재[석적](?:의원)?(\d+)(?:인|명|분)?(?:중에|중|가운데|으로)?[,，]?"
    r"(?:전원일치찬성|전원찬성|전원일치|만장일치|(\d+)(?:인|명)찬성)")
LEAD_RE = re.compile(r"^(?:[,，.]|입니다|으로서|으로|로|이므로|그래서|따라서|그러므로|그러니까)+")
TRAIL_RE = re.compile(r"(?:은|는)(?:[^.]{0,40}?(?:수정안대로|원안대로))?$")
MARKER_RE = re.compile(r"\((?:[^()]{0,20})성명은끝에실음\)")
AGENDA_HEAD_RE = re.compile(r"^\s*(\d{1,3})\.\s*(\S.*)$")
TIME_END_RE = re.compile(r"\(\s*\d+\s*[시時]\s*\d+\s*[분分]\s*(산\s*회|散\s*會)\s*\)")
NOTE_ACTUAL_RE = re.compile(r"실[제체]")
DAY_PASSED_RE = re.compile(r"^\s*\(\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*24\s*시\s*경\s*과\s*\)\s*$")


def nfkc(s):
    return unicodedata.normalize("NFKC", s) if isinstance(s, str) else s


def read_lines(pdf_path: Path) -> list[str]:
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    lines: list[str] = []
    for page in doc:
        for ln in nfkc(page.get_text()).split("\n"):
            if PAGE_HDR_RE.match(ln):
                continue
            lines.append(ln.rstrip())
    doc.close()
    return lines


def line_tokens(line: str) -> list[str]:
    """Split a line of names into tokens.

    Names are separated by two or more spaces. Most minutes print a name
    without spaces ('강기윤  강기정', a two-syllable name as '김  현'). Some
    17th-Assembly minutes space every syllable ('문 희 상   민 병 두', a
    two-syllable name as '문    희'). A chunk whose single-space pieces are
    all one syllable is one name, and otherwise each piece is a token.
    """
    out = []
    for chunk in re.split(r"\s{2,}", line.strip()):
        if not chunk:
            continue
        pieces = chunk.split()
        if len(pieces) > 1 and all(len(p) == 1 for p in pieces):
            out.append("".join(pieces))
        else:
            out += pieces
    return out


def tokens_to_names(tokens: list[str], known: set | None = None) -> tuple[list[str], list[str]]:
    """Join spaced two-syllable names ('윤 영' -> '윤영'). Returns (names, junk).

    With `known`, two single syllables are joined only into a member's name.
    """
    names, junk = [], []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if len(t) == 1 and re.match(r"[가-힣一-鿿]", t):
            if (i + 1 < len(tokens) and len(tokens[i + 1]) == 1
                    and (not known or t + tokens[i + 1] in known)):
                names.append(t + tokens[i + 1])
                i += 2
                continue
            junk.append(t)
            i += 1
            continue
        if HANGUL_NAME.match(t) or HANJA_NAME.match(t):
            names.append(t)
        else:
            junk.append(t)
        i += 1
    return names, junk


@dataclass
class Group:
    label: str
    n_printed: int
    names: list[str] = field(default_factory=list)
    junk: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)

    def finalize(self, known: set | None = None):
        """Names from the collected lines.

        Dropped (and listed in `dropped`): lines with digits (page furniture
        and result tables), and, when `known` (the Hangul and Hanja names of
        the assembly's members) is given, lines of which fewer than half the
        name-like tokens are members' names (prose printed after the last
        list). When the names still outnumber the printed count, runs of two
        or more lines with at most one token are dropped as text interleaved
        from elsewhere on the page.
        """
        parsed = []
        for ln in self.lines:
            nm, jk = tokens_to_names(line_tokens(ln), known)
            prose = bool(known) and bool(nm) and sum(x in known for x in nm) * 2 < len(nm)
            parsed.append((ln, bool(re.search(r"\d", ln)) or prose, len(nm) + len(jk) <= 1))
        keep = [not p[1] for p in parsed]

        def stream(flags):
            toks = []
            for q, p in enumerate(parsed):
                if flags[q]:
                    toks += line_tokens(p[0])
            return tokens_to_names(toks, known)

        names, junk = stream(keep)
        if len(names) > self.n_printed:
            k = 0
            while k < len(parsed):
                if parsed[k][2]:
                    j = k
                    while j < len(parsed) and parsed[j][2]:
                        j += 1
                    if j - k >= 2:
                        for q in range(k, j):
                            keep[q] = False
                    k = j
                else:
                    k += 1
            names, junk = stream(keep)
        self.names, self.junk = names, junk
        self.dropped = [p[0] for q, p in enumerate(parsed) if not keep[q]]


@dataclass
class Event:
    title: str
    line_no: int
    revote_seq: int = 1
    groups: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def split_appendix(lines: list[str]) -> tuple[int, list[int]]:
    """(end of the body, line numbers of the roll-call headings)."""
    heads = [i for i, ln in enumerate(lines) if ROLLCALL_HEAD_RE.search(ln)]
    first = heads[0] if heads else len(lines)
    ends = [i for i, ln in enumerate(lines[:first]) if TIME_END_RE.search(ln)]
    body_end = ends[-1] + 1 if ends else first
    return body_end, heads


def parse_rollcall_section(lines: list[str], start: int, known: set | None = None) -> list[Event]:
    events: list[Event] = []
    i, n = start + 1, len(lines)
    cur: Event | None = None
    cur_group: Group | None = None
    title_buf: list[str] = []
    in_title = False
    note_buf: list[str] | None = None
    pending_notes: list[str] = []
    revote = 1
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if note_buf is not None:
            # A note normally ends with ')'. Some notes lose it in the PDF
            # text, so a ◯ title, a group label or a 【 heading also ends one.
            if s[0] in CIRCLE or LABEL_RE.match(s) or s.startswith("【"):
                if cur is not None:
                    cur.notes.append("".join(note_buf))
                note_buf = None
            else:
                note_buf.append(s)
                if s.endswith(")"):
                    if cur is not None:
                        cur.notes.append("".join(note_buf))
                    note_buf = None
                i += 1
                continue
        if s.startswith("【") and not ROLLCALL_HEAD_RE.search(s):
            break
        if s[0] in CIRCLE:
            title_buf, in_title, pending_notes = [s[1:]], True, []
            cur_group = cur = None
            revote = 1
            i += 1
            continue
        m = LABEL_RE.match(s)
        if m:
            label, cnt, rest = m.group(1), int(m.group(2)), m.group(3)
            if in_title:
                cur = Event(title="".join(title_buf).strip(), line_no=i, notes=pending_notes)
                events.append(cur)
                in_title = False
                pending_notes = []
            elif cur is not None and label == "투표" and "투표" in cur.groups:
                revote += 1
                cur = Event(title=cur.title, line_no=i, revote_seq=revote, notes=pending_notes)
                events.append(cur)
                pending_notes = []
            if cur is None:
                i += 1
                continue
            cur_group = Group(label=label, n_printed=cnt)
            if label in cur.groups:
                cur_group.junk.append(f"<duplicate label {label}>")
            cur.groups[label] = cur_group
            if rest.strip():
                cur_group.lines.append(rest.strip())
            i += 1
            continue
        if in_title and REVOTE_RE.match(s):
            pending_notes.append(s)       # '<1차 투표>' between the title and the counts
            i += 1
            continue
        if in_title:
            if re.search(r"의원\s*\(\d+인\)\s*$", "".join(title_buf)):
                in_title = False          # ◯출석 의원(281인) and similar lists
            else:
                title_buf.append(s)
            i += 1
            continue
        if s.startswith("("):
            note_buf = [s]
            if s.endswith(")"):
                if cur is not None:
                    cur.notes.append(s)
                note_buf = None
            i += 1
            continue
        if REVOTE_RE.match(s):
            pending_notes.append(s)       # '<2차 투표>' before the repeated counts
            i += 1
            continue
        if cur_group is not None:
            cur_group.lines.append(s)
        i += 1
    for e in events:
        for g in e.groups.values():
            g.finalize(known)
    return events


def parse_body(lines: list[str], body_end: int, meeting_date: str | None = None):
    """Chair announcements with their marker flag, the agenda heading in force
    and the date in force: the meeting date, advanced by each
    '(2월23일 24시 경과)' printed when a sitting runs past midnight."""
    chars, line_of, agenda_at_line, date_at_line = [], [], [], []
    cur_agenda = None
    cur_date = meeting_date
    for i, ln in enumerate(lines[:body_end]):
        m = AGENDA_HEAD_RE.match(ln)
        if m and not ln.startswith(" "):
            cur_agenda = (int(m.group(1)), m.group(2).strip())
        agenda_at_line.append(cur_agenda)
        md = DAY_PASSED_RE.match(ln)
        if md and cur_date:
            d = pd.Timestamp(int(cur_date[:4]), int(md.group(1)), int(md.group(2)))
            cur_date = (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        date_at_line.append(cur_date)
        for ch in ln:
            if not ch.isspace():
                chars.append(ch)
                line_of.append(i)
    text = "".join(chars)
    hits = []
    for m in HEAD_RE.finditer(text):
        # the counts follow '재석 N인 중' in any order, up to the end of the clause
        win = text[m.end(): m.end() + 90]
        ce = CLAUSE_END_RE.search(win)
        clause = win[: ce.start()] if ce else win
        y = YES_RE.search(clause)
        if y is None:
            continue
        no, ab = NO_RE.search(clause), ABSTAIN_RE.search(clause)
        last = max(x.end() for x in (y, no, ab) if x is not None)
        nil = NIL_RE.match(clause, last)
        if nil:
            last = nil.end()
        hits.append((m.start(), m.end() + last, int(m.group(1)), int(y.group(1) or y.group(2)),
                     no.group(1) if no else None, ab.group(1) if ab else None, "counts"))
    taken = {h[0] for h in hits}
    for m in UNANIMOUS_RE.finditer(text):
        if m.start() in taken:
            continue
        if m.group(2) is not None and m.group(2) != m.group(1):
            continue
        n = int(m.group(1))
        hits.append((m.start(), m.end(), n, n, None, None, "unanimous"))
    hits.sort()
    anns = []
    for i, (start, end, present, yes, no, abst, kind) in enumerate(hits):
        ln = line_of[start]
        tail = text[end: end + 320]
        mr = re.search(r"(가결|부결)(?:되었|었음)", tail)    # '가결었음' is a typo in 31699
        ann_result_far = None
        if mr is None:
            # A page header can push the declaration past the window (17_28296_002,
            # 18_34089_006). Look further, but never into the next announcement.
            nxt = hits[i + 1][0] if i + 1 < len(hits) else len(text)
            far = re.search(r"(가결|부결)(?:되었|었음)", text[end: min(end + 900, nxt)])
            ann_result_far = far.group(1) if far else None
        span = tail[: mr.start()] if mr else None
        if span is not None:
            span_clean = TRAIL_RE.sub("", LEAD_RE.sub("", span))
        else:
            span_clean = None
        anns.append({
            "pos": start, "line": ln, "present": present, "yes": yes,
            "no": int(no or 0), "abstain": int(abst or 0),
            "ann_title": span_clean, "ann_clause": span,
            "ann_result": mr.group(1) if mr else ann_result_far, "ann_kind": kind,
            "pre_ctx": text[max(0, start - 400): start],
            "agenda_no": agenda_at_line[ln][0] if agenda_at_line[ln] else None,
            "agenda_text": agenda_at_line[ln][1] if agenda_at_line[ln] else None,
            "date": date_at_line[ln],
            "marker": False,
        })
    markers = [m.start() for m in MARKER_RE.finditer(text)]
    orphans = 0
    prev = -1
    for mp in markers:
        cands = [a for a in anns if prev < a["pos"] < mp]
        if cands:
            cands[-1]["marker"] = True
        else:
            orphans += 1
        prev = mp
    return anns, len(markers), orphans


def parse_pdf(pdf_path: Path, known: set | None = None, meeting_date: str | None = None) -> dict:
    lines = read_lines(pdf_path)
    body_end, heads = split_appendix(lines)
    events: list[Event] = []
    for h in heads:
        events += parse_rollcall_section(lines, h, known)
    anns, n_markers, n_orphans = parse_body(lines, body_end, meeting_date)
    return {"n_lines": len(lines), "body_end": body_end, "n_heads": len(heads),
            "events": events, "announcements": anns, "n_markers": n_markers,
            "n_orphan_markers": n_orphans}


# ── titles ──────────────────────────────────────────────────────────────

def _hanja_to_hangul(s: str) -> str:
    try:
        import hanja
    except ImportError as e:  # pragma: no cover
        raise SystemExit("minutes_votes needs the `hanja` package to read Hanja titles "
                         "(pip install hanja)") from e
    return hanja.translate(s, "substitution")


def hangul_title(s) -> str:
    """NFKC, with Hanja read in Hangul."""
    if not isinstance(s, str):
        return ""
    s = nfkc(s)
    if re.search(r"[一-鿿]", s):
        s = _hanja_to_hangul(s)
    return s


_YI = {2, 3, 6, 7, 12, 17, 20}   # medials ㅑ ㅒ ㅕ ㅖ ㅛ ㅠ ㅣ


def dueum(s: str) -> str:
    """Fold initial ㄹ and ㄴ as the initial-sound law does ('년금' and '연금'
    compare equal). Applied to both sides of a title comparison, because Hanja
    titles read syllable by syllable ('國民年金法' -> '국민년금법')."""
    out = []
    for ch in s:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            ini, med, fin = c // 588, (c % 588) // 28, c % 28
            if ini == 5:                       # ㄹ
                ini = 11 if med in _YI else 2
            elif ini == 2 and med in _YI:      # ㄴ before i/y
                ini = 11
            ch = chr(0xAC00 + ini * 588 + med * 28 + fin)
        out.append(ch)
    return "".join(out)


def norm_title(s) -> str:
    return dueum(re.sub(r"[\s「」『』<>《》〈〉\"'“”‘’.·ㆍᆞㆍ‧․・,，\ua854\ua855()\[\]]", "", hangul_title(s)))


def strip_proposer(s: str) -> str:
    """Drop trailing '(…제출)', '(…의원 외 N인 발의)', '[법률 제242호]' and similar."""
    return re.sub(r"(\((?!대안\))[^()]*\)|\[[^\[\]]*\])+$", "", s)


def sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ── events <-> chair announcements ──────────────────────────────────────

def score_pair(t, a, p):
    if t and a and (t in a or (len(a) > 5 and a in t)):
        return 1.0
    if t and p and t in p:
        return 0.9
    return sim(t, a)


def align_meeting(ev: list[dict], an: list[dict]) -> list[tuple[int, int | None, str]]:
    """(event index, announcement index or None, method) for every event.

    'order': the meeting has as many marked announcements as appendix votes
    and every pair in print order agrees on the title (score >= 0.9).
    Otherwise 'title': a one-to-one assignment on the title score (>= 0.6),
    best score first, then marked announcements, then the pair nearest in
    order, because the appendix sometimes prints votes in a different order
    from the body. Between announcements that score the same for a vote (a repeated
    title), the one whose 재석 equals the number of names printed is taken
    first. Votes left over are paired in order with the marked announcements
    left over when both number the same ('order_rest'), else 'unaligned'.
    """
    marked = [j for j, a in enumerate(an) if a["marker"]]
    et = [norm_title(strip_proposer(nfkc(e["title"]))) for e in ev]
    at = [norm_title(a["ann_title"]) for a in an]
    pc = [norm_title(a["pre_ctx"]) for a in an]
    if len(ev) == len(marked) and all(
            score_pair(et[i], at[j], pc[j]) >= 0.9 for i, j in zip(range(len(ev)), marked)):
        return [(i, j, "order") for i, j in zip(range(len(ev)), marked)]
    n, m = len(ev), len(an)
    cands = []
    for i in range(n):
        for j in range(m):
            sc = score_pair(et[i], at[j], pc[j])
            if sc >= 0.6:
                same_n = ev[i].get("n_names") == an[j]["present"]
                cands.append((-sc, not an[j]["marker"], not same_n,
                              abs(i / max(n, 1) - j / max(m, 1)), i, j))
    cands.sort()
    pairs, used = {}, set()
    for *_, i, j in cands:
        if i not in pairs and j not in used:
            pairs[i] = j
            used.add(j)
    how = {i: "title" for i in pairs}
    rest_e = [i for i in range(n) if i not in pairs]
    rest_a = [j for j in marked if j not in used]
    if rest_e and len(rest_e) == len(rest_a):
        for i, j in zip(rest_e, rest_a):
            pairs[i], how[i] = j, "order_rest"
    return [(e, pairs.get(e), how.get(e, "unaligned")) for e in range(n)]


def note_counts_match(note: str, names: dict) -> bool | None:
    """Do the 'actual' counts of a correction note equal the name counts?"""
    if not isinstance(note, str) or not NOTE_ACTUAL_RE.search(note):
        return None
    txt = re.sub(r"\s", "", NOTE_ACTUAL_RE.split(note, maxsplit=1)[1])
    seen = 0
    for lab, v in names.items():
        m = re.search(lab + r"의원(\d+)인", txt)
        if m:
            seen += 1
            if int(m.group(1)) != v:
                return False
        elif re.search(lab + r"의원없음", txt):
            seen += 1
            if v != 0:
                return False
    return True if seen else None


# ── bills ───────────────────────────────────────────────────────────────

def load_bills(age: int, master_dir: Path, raw_dir: Path) -> pd.DataFrame:
    mb = pd.read_parquet(master_dir / f"master_bills_{age}.parquet",
                         columns=["bill_id", "bill_no", "bill_nm", "bill_kind", "ppsl_dt",
                                  "rgs_rsln_dt", "proc_dt", "rgs_conf_rslt", "plenary_decided"])
    ymd = lambda c: pd.to_datetime(mb[c]).dt.strftime("%Y-%m-%d")  # noqa: E731
    mb["date"], mb["pdate"], mb["ppsl"] = ymd("rgs_rsln_dt"), ymd("proc_dt"), ymd("ppsl_dt")
    mb["ppsl"] = mb["ppsl"].fillna("0000-00-00")
    nz = pd.read_parquet(raw_dir / f"nzpltgfqabtcpsmai_{age}.parquet", columns=["BILL_ID", "PROC_DT"])
    nz = nz.rename(columns={"BILL_ID": "bill_id", "PROC_DT": "nz_proc_dt"}).drop_duplicates("bill_id")
    mb = mb.merge(nz, on="bill_id", how="left")
    mb["last"] = mb[["date", "pdate", "nz_proc_dt"]].fillna("").max(axis=1).replace("", "9999-12-31")
    mb["key"] = mb["bill_nm"].map(norm_title)
    mb["key_np"] = mb["bill_nm"].map(lambda s: norm_title(strip_proposer(nfkc(s))))
    return mb


MOTION_RE = re.compile(r"(.*?)(?:에\s*대한|의)\s*(수정안|번안)")


def title_kind(title: str) -> tuple[str, str]:
    """('bill' | 'amendment' | 'reversal', title of the bill voted on)."""
    t = hangul_title(title)
    m = MOTION_RE.search(t)
    if m:
        return ("amendment" if m.group(2) == "수정안" else "reversal"), m.group(1)
    return "bill", t


def link_bill(title: str, ann_title, on_date: pd.DataFrame, pending: pd.DataFrame) -> dict:
    """Link one vote to a bill.

    on_date holds the bills decided on the vote date, pending the bills
    proposed on or before the date and decided on or after it.
    """
    kind, parent = title_kind(title)
    keys = []
    for t in [parent, ann_title if kind == "bill" else None]:
        if isinstance(t, str) and t:
            keys += [norm_title(t), norm_title(strip_proposer(hangul_title(t)))]
    keys = [k for k in dict.fromkeys(keys) if k]
    decided = on_date[on_date["plenary_decided"] == 1]
    for pool, tag in [(decided, "decided"), (on_date, "any"), (pending, "pending")]:
        for k in keys:
            hit = pool[(pool["key"] == k) | (pool["key_np"] == k)]
            if len(hit) == 1:
                return {"bill_link": f"exact_{tag}", "vote_kind": kind,
                        "bill_id": hit.iloc[0]["bill_id"], "bill_link_score": 1.0}
            if len(hit) > 1:
                return {"bill_link": f"ambiguous_{tag}", "vote_kind": kind,
                        "bill_candidates": ",".join(hit["bill_id"])}
    if on_date.empty:
        return {"bill_link": "no_bill_on_date", "vote_kind": kind}
    best, arg = 0.0, None
    for _, b in decided.iterrows():
        for k in keys:
            sc = max(sim(k, b["key"]), sim(k, b["key_np"]))
            if sc > best:
                best, arg = sc, b
    if arg is not None and best >= 0.85:
        return {"bill_link": "fuzzy", "vote_kind": kind, "bill_id": arg["bill_id"],
                "bill_link_score": round(best, 3)}
    return {"bill_link": "unlinked", "vote_kind": kind,
            "bill_link_score": round(best, 3) if arg is not None else None}


# ── members ─────────────────────────────────────────────────────────────

def load_roster(age: int, members_dir: Path) -> pd.DataFrame:
    mem = pd.read_parquet(members_dir / f"members_{age}.parquet",
                          columns=["mona_cd", "member_name", "member_name_hanja", "party", "district"])
    if mem["mona_cd"].duplicated().any():
        raise SystemExit(f"members_{age} has more than one row per mona_cd")
    mem["hanja_n"] = mem["member_name_hanja"].map(nfkc).str.strip().replace("", None)
    return mem


def resolve_names(nm: pd.DataFrame, mem: pd.DataFrame, age: int) -> pd.DataFrame:
    """Add member_id and member_match to the printed names of one assembly."""
    rules = SAME_NAME.get(age, {})
    by_name = mem.groupby("member_name")["mona_cd"].apply(list).to_dict()
    hj = mem.dropna(subset=["hanja_n"])
    if hj["hanja_n"].duplicated().any():
        raise SystemExit(f"members_{age}: two members share a Hanja name")
    by_hanja = dict(zip(hj["hanja_n"], hj["mona_cd"]))
    shared = {n: cs for n, cs in by_name.items() if len(cs) > 1}
    if set(shared) != set(rules) or any(set(cs) != set(rules[n]) for n, cs in shared.items()):
        raise SystemExit(f"members_{age}: same-name members {shared} differ from SAME_NAME[{age}]")
    period = {c: p for r in rules.values() for c, p in r.items()}
    hanja_of = {n: {c: mem.loc[mem["mona_cd"] == c, "hanja_n"].iloc[0] for c in cs}
                for n, cs in shared.items()}

    aliases = ALIASES.get(age, {})
    for printed, name in aliases.items():
        if printed in by_name or len(by_name.get(name, [])) != 1:
            raise SystemExit(f"ALIASES[{age}]: {printed} -> {name} is not a one-member spelling")
    ids, how = [], []
    for name, date in zip(nm["name_raw"], nm["date"]):
        if name in aliases:
            ids.append(by_name[aliases[name]][0]); how.append("name_spelling")
            continue
        if name in by_hanja:
            c = by_hanja[name]
            if c in period and not seated(period[c], date):
                raise SystemExit(f"{age}th: {name} ({c}) printed on {date}, outside the seat "
                                 f"dates in SAME_NAME")
            ids.append(c); how.append("hanja")
            continue
        cs = by_name.get(name)
        if not cs:
            ids.append(None); how.append("unmatched")
        elif len(cs) == 1:
            ids.append(cs[0]); how.append("name")
        else:
            on = [c for c in cs if seated(period[c], date)]
            if len(on) == 1:
                ids.append(on[0]); how.append("same_name_seated_alone")
            elif not on:
                raise SystemExit(f"{age}th: {name} printed on {date}, when SAME_NAME seats neither member")
            else:
                ids.append(None); how.append("pending")
    nm = nm.assign(member_id=ids, member_match=how)

    for name, cs in shared.items():
        form_to_member = {h: c for c, h in hanja_of[name].items()}
        pend = (nm["member_match"] == "pending") & (nm["name_raw"] == name)
        if not pend.any():
            continue
        in_ev = nm[nm["vote_event_id"].isin(nm.loc[pend, "vote_event_id"])
                   & (nm["name_raw"].isin(list(form_to_member)) | pend)]
        for ev_id, d in in_ev.groupby("vote_event_id"):
            hg = d[d["member_match"] == "pending"]
            if hg.empty:
                continue
            printed_hj = {form_to_member[x] for x in d["name_raw"] if x in form_to_member}
            if len(printed_hj) == 1 and len(hg) == 1:
                other = [c for c in cs if c not in printed_hj][0]
                nm.loc[hg.index, ["member_id", "member_match"]] = [other, "same_name_event_hanja"]
            elif len(printed_hj) == 0 and len(hg) == 2 and hg["vote"].nunique() == 1:
                nm.loc[hg.index[0], ["member_id", "member_match"]] = [cs[0], "same_name_pair_same_vote"]
                nm.loc[hg.index[1], ["member_id", "member_match"]] = [cs[1], "same_name_pair_same_vote"]
            else:
                nm.loc[hg.index, ["member_id", "member_match"]] = [None, "unresolved_same_name"]
    left = nm["member_match"] == "pending"
    nm.loc[left, "member_match"] = "unresolved_same_name"
    return nm


# ── one assembly ────────────────────────────────────────────────────────

GROUPS = [("투표", "total"), ("찬성", "yes"), ("반대", "no"), ("기권", "abstain")]


def build_term(age: int, meetings: pd.DataFrame, pdf_dir: Path, fetched: dict, *,
               members_dir: Path, master_dir: Path, raw_dir: Path):
    """Parse, link and validate every meeting of one assembly.

    Returns (events, votes, meetings) data frames.
    """
    mem = load_roster(age, members_dir)
    known = set(mem["member_name"]) | set(mem["hanja_n"].dropna()) | set(ALIASES.get(age, {}))
    ev_rows, nm_rows, mt_rows = [], [], []
    for _, m in meetings.iterrows():
        cn = int(m["confer_num"])
        pdf = pdf_dir / f"{cn}.pdf"
        rec = fetched.get(cn, {})
        base = {"age": age, "confer_num": cn, "conf_id": m["conf_id"], "meeting_date": m["date"],
                "meeting_title": m["title"]}
        mrow = {**{k: m[k] for k in meetings.columns}, "pdf_status": rec.get("status"),
                "pdf_bytes": rec.get("bytes"), "pdf_sha256": rec.get("sha256")}
        if not pdf.exists():
            mrow["pdf_status"] = mrow["pdf_status"] or "missing"
            mt_rows.append(mrow)
            continue
        r = parse_pdf(pdf, known, m["date"])
        evs = [{"title": e.title, "revote_seq": e.revote_seq, "notes": e.notes,
                "groups": e.groups,
                "n_names": sum(len(g.names) for lab, g in e.groups.items() if lab != "투표")}
               for e in r["events"]]
        anns = r["announcements"]
        align = align_meeting(evs, anns)
        for (k, e), (_, aj, how) in zip(enumerate(evs, start=1), align):
            row = {**base, "vote_event_id": f"{age}_{cn}_{k:03d}", "event_seq": k,
                   "revote_seq": e["revote_seq"], "title": e["title"],
                   "appendix_note": " | ".join(e["notes"]) or None}
            junk, dropped = [], []
            for lab, key in GROUPS:
                g = e["groups"].get(lab)
                row[f"printed_{key}"] = g.n_printed if g else (None if lab == "투표" else 0)
                if g:
                    junk += [f"{lab}:{x}" for x in g.junk]
                    dropped += [f"{lab}:{x}" for x in g.dropped]
                    if lab == "투표" and g.names:
                        junk += [f"투표:{x}" for x in g.names]
                if g and lab != "투표":
                    for j, name in enumerate(g.names, start=1):
                        nm_rows.append({"age": age, "vote_event_id": row["vote_event_id"],
                                        "confer_num": cn, "event_seq": k,
                                        "vote": lab, "name_seq": j, "name_raw": name})
            row["junk_tokens"] = " ".join(junk) or None
            row["dropped_lines"] = (" / ".join(dropped)[:1000]) or None
            row["chair_align"] = how
            a = anns[aj] if aj is not None else None
            for key in ["present", "yes", "no", "abstain"]:
                row[f"chair_{key}"] = a[key] if a else None
            row["date"] = a["date"] if a else m["date"]
            row["chair_result"] = a["ann_result"] if a else None
            row["chair_title"] = a["ann_title"] if a else None
            row["chair_clause"] = a["ann_clause"] if a else None
            row["agenda_no"] = a["agenda_no"] if a else None
            row["agenda_text"] = a["agenda_text"] if a else None
            row["chair_title_score"] = round(score_pair(
                norm_title(strip_proposer(nfkc(e["title"]))), norm_title(a["ann_title"]),
                norm_title(a["pre_ctx"])), 3) if a else None
            ev_rows.append(row)
        mrow.update(n_lines=r["n_lines"], n_rollcall_heads=r["n_heads"], n_events=len(evs),
                    n_announcements=len(anns),
                    n_marked_announcements=sum(a["marker"] for a in anns),
                    n_markers=r["n_markers"], n_orphan_markers=r["n_orphan_markers"])
        mt_rows.append(mrow)

    E = pd.DataFrame(ev_rows)
    N = pd.DataFrame(nm_rows)
    M = pd.DataFrame(mt_rows)

    # members (the vote date decides which same-name members were seated)
    N = N.merge(E[["vote_event_id", "date"]], on="vote_event_id", how="left")
    N = resolve_names(N, mem, age)
    N = N.merge(mem[["mona_cd", "member_name"]].rename(columns={"mona_cd": "member_id"}),
                on="member_id", how="left")
    N["member_name"] = N["member_name"].fillna(N["name_raw"])
    N, printed_twice = drop_printed_twice(N, age)
    E["names_printed_twice"] = E["vote_event_id"].map(printed_twice)
    unresolved = N[N["member_id"].isna()].groupby("vote_event_id").size()
    E["n_names_unresolved"] = E["vote_event_id"].map(unresolved).fillna(0).astype("int64")

    # counts and flags (names counted after drop_printed_twice)
    cnt = N.groupby(["vote_event_id", "vote"]).size().unstack(fill_value=0)
    for lab, key in GROUPS[1:]:
        col = cnt[lab] if lab in cnt.columns else pd.Series(dtype="int64")
        E[f"names_{key}"] = E["vote_event_id"].map(col).fillna(0).astype("int64")
    E["names_total"] = E["names_yes"] + E["names_no"] + E["names_abstain"]
    E["names_equal_printed"] = ((E["names_yes"] == E["printed_yes"]) & (E["names_no"] == E["printed_no"])
                                & (E["names_abstain"] == E["printed_abstain"]))
    has = E["chair_present"].notna()
    agree = (has & (E["names_total"] == E["chair_present"]) & (E["names_yes"] == E["chair_yes"])
             & (E["names_no"] == E["chair_no"]) & (E["names_abstain"] == E["chair_abstain"]))
    E["chair_counts_differ"] = pd.array([None if not h else (not a) for h, a in zip(has, agree)],
                                        dtype="boolean")
    E["correction_note"] = E["appendix_note"].fillna("").str.contains(NOTE_ACTUAL_RE)
    E["correction_note_matches_names"] = pd.array(
        [note_counts_match(n, {"투표": t, "찬성": y, "반대": no, "기권": ab})
         for n, t, y, no, ab in zip(E["appendix_note"], E["names_total"], E["names_yes"],
                                    E["names_no"], E["names_abstain"])], dtype="boolean")

    # bills
    bills = load_bills(age, master_dir, raw_dir)
    links = []
    for d, sub in E.groupby("date", sort=False):
        on_date = bills[(bills["date"] == d) | (bills["pdate"] == d) | (bills["nz_proc_dt"] == d)]
        pending = bills[(bills["ppsl"] <= d) & (bills["last"] >= d)]
        for idx, r in sub.iterrows():
            links.append((idx, link_bill(r["title"], r["chair_title"], on_date, pending)))
    L = pd.DataFrame([x for _, x in links], index=[i for i, _ in links]).reindex(E.index)
    for c in ["bill_link", "vote_kind", "bill_id", "bill_link_score", "bill_candidates"]:
        E[c] = L[c] if c in L.columns else None
    E = E.merge(bills[["bill_id", "bill_no", "bill_nm", "bill_kind", "rgs_conf_rslt"]],
                on="bill_id", how="left")
    E["vote_on"] = E["vote_kind"]
    E["vote_type"] = E["vote_kind"].map({"bill": "original", "amendment": "amendment",
                                         "reversal": "reversal"})
    E.loc[E["revote_seq"] > 1, "vote_type"] = "revote"
    E.loc[E["bill_id"].isna(), "vote_type"] = "other"

    for c in ["printed_total", "agenda_no", "chair_present", "chair_yes", "chair_no", "chair_abstain"]:
        E[c] = E[c].astype("Int64")
    E = E[EVENT_COLS]
    N = N[VOTE_COLS].sort_values(["confer_num", "event_seq", "vote", "name_seq"],
                                 key=lambda s: s.map(VOTE_ORDER) if s.name == "vote" else s,
                                 kind="mergesort").reset_index(drop=True)
    return E, N, M


def drop_printed_twice(N: pd.DataFrame, age: int) -> tuple[pd.DataFrame, pd.Series]:
    """A name printed twice in one vote (a misprint of the list).

    Matched by a unique name or a Hanja form, on the same list: the second
    row is dropped and the name recorded in the event's names_printed_twice.
    On two different lists the source does not say how the member voted, so
    both rows keep member_id null with member_match 'printed_on_two_lists'.
    A repeat created by a same-name rule would mean a wrong rule and stops
    the build.
    """
    known = N[N["member_id"].notna()]
    twice = known[known.duplicated(["vote_event_id", "member_id"], keep=False)]
    if twice.empty:
        return N, pd.Series(dtype=object)
    bad = twice[~twice["member_match"].isin(["name", "hanja"])]
    if len(bad):
        raise SystemExit(f"{age}th: a same-name rule puts a member twice in one vote:\n"
                         + bad.to_string())
    N = N.copy()
    drop, recorded = [], {}
    for (ev, mid), d in twice.groupby(["vote_event_id", "member_id"]):
        if d["vote"].nunique() == 1:
            drop += list(d.index[1:])
        else:
            N.loc[d.index, ["member_id", "member_match"]] = [None, "printed_on_two_lists"]
        recorded.setdefault(ev, []).append(d["name_raw"].iloc[0])
    return N.drop(index=drop), pd.Series({k: ",".join(v) for k, v in recorded.items()})


VOTE_ORDER = {"찬성": 0, "반대": 1, "기권": 2}


EVENT_COLS = [
    "age", "vote_event_id", "confer_num", "conf_id", "meeting_date", "date", "meeting_title",
    "event_seq",
    "revote_seq", "title", "agenda_no", "agenda_text",
    "vote_type", "vote_on", "bill_id", "bill_no", "bill_nm", "bill_kind", "bill_link", "bill_link_score",
    "bill_candidates", "rgs_conf_rslt",
    "printed_total", "printed_yes", "printed_no", "printed_abstain",
    "names_total", "names_yes", "names_no", "names_abstain", "names_equal_printed",
    "names_printed_twice", "n_names_unresolved",
    "chair_align", "chair_title", "chair_title_score", "chair_present", "chair_yes", "chair_no",
    "chair_abstain", "chair_result", "chair_counts_differ",
    "appendix_note", "correction_note", "correction_note_matches_names",
    "junk_tokens", "dropped_lines", "chair_clause",
]
VOTE_COLS = ["age", "vote_event_id", "confer_num", "date", "event_seq", "vote", "name_seq",
             "name_raw", "member_name", "member_id", "member_match"]


def summary_lines(age: int, E: pd.DataFrame, N: pd.DataFrame, M: pd.DataFrame) -> list[str]:
    has = E["chair_present"].notna()
    out = [
        f"meetings {len(M)}, with a PDF {int(M['n_lines'].notna().sum())}, "
        f"with a roll-call appendix {int((M['n_rollcall_heads'].fillna(0) > 0).sum())}",
        f"votes {len(E):,}, names {len(N):,}, names equal printed counts in "
        f"{int(E['names_equal_printed'].sum()):,}",
        f"chair counts found for {int(has.sum()):,}, equal to the names in "
        f"{int((E['chair_counts_differ'] == False).sum()):,}, differ in "  # noqa: E712
        f"{int((E['chair_counts_differ'] == True).sum()):,} "  # noqa: E712
        f"({int(((E['chair_counts_differ'] == True) & (E['correction_note_matches_names'] == True)).sum()):,} "  # noqa: E712
        f"explained by a correction note)",
        f"bill link {E['bill_link'].value_counts().to_dict()}",
        f"vote_type {E['vote_type'].value_counts().to_dict()}",
        f"member_match {N['member_match'].value_counts().to_dict()}",
    ]
    return out
