#!/usr/bin/env python3
"""seat-watch: watch full class sections and report when a seat opens.

Standard library only. State lives under HOME so it survives restarts and Skill updates.
Seat truth for ASU is ENRLTOT / ENRLCAP / ENRLSTAT (never seatInfo; it disagrees with the status flag).

Exit codes (SKILL.md maps each to a reply):
  0 no change (send the student nothing)    10 change printed
  2 bad arguments                           3 school site unreachable or not 200
  4 response shape changed                  5 nothing is being watched
  6 class number not found
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

API = "https://eadvs-cscc-catalog-api.apps.asu.edu/catalog-microservices/api/v1/search/classes"
HEADERS = {"Authorization": "Bearer null",  # what the public class-search page itself sends
           "User-Agent": "seat-watch/0.1 (student hackathon project; low-rate, read-only)"}
DAYS = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5, "Su": 6}
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")
MAX_WATCHES = 5


class Fail(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


# ---------- parsing helpers ----------

def parse_days(value):
    """ASU gives ['M W'], ['T Th'], [''] or '&nbsp;'. Also accepts 'MWF'-style from busy files."""
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    value = (value or "").replace("&nbsp;", " ").strip()
    if not value:
        return []
    toks = value.split()
    if len(toks) == 1 and len(toks[0]) > 2 and toks[0] not in DAYS:
        toks = re.findall(r"Th|Sa|Su|M|T|W|F", toks[0])
    return sorted({DAYS[t] for t in toks if t in DAYS})


def parse_time(value):
    """'9:00 AM' / '09:00' / None -> minutes after midnight, or None."""
    if not value or str(value).strip() in ("None", "&nbsp;"):
        return None
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])?\s*$", str(value))
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap:
        h = h % 12 + (12 if ap.lower() == "pm" else 0)
    return h * 60 + mi


def fmt_time(minutes):
    if minutes is None:
        return "?"
    h, m = divmod(minutes, 60)
    return "%d:%02d %s" % ((h % 12) or 12, m, "AM" if h < 12 else "PM")


def fmt_days(days):
    names = {v: k for k, v in DAYS.items()}
    return " ".join(names[d] for d in days)


def fmt_when(sec):
    if not sec["days"] or sec["start"] is None:
        return "no set meeting time (online/async)"
    return "%s %s-%s" % (fmt_days(sec["days"]), fmt_time(sec["start"]), fmt_time(sec["end"]))


def to_int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def normalize_asu(c):
    try:
        x = c["CLAS"]
        sec = {
            "term": str(x["STRM"]), "subject": x["SUBJECT"], "number": str(x["CATALOGNBR"]),
            "class_nbr": str(x["CLASSNBR"]), "section": str(x["CLASSSECTION"]),
            "comp": x.get("COMPONENTPRIMARY") or "", "title": x.get("TITLE") or "",
            "status": x["ENRLSTAT"], "enrl": to_int(x["ENRLTOT"]), "cap": to_int(x["ENRLCAP"]),
            "days": parse_days(c.get("DAYLIST")), "start": parse_time(x.get("STARTTIME")),
            "end": parse_time(x.get("ENDTIME")), "mode": x.get("INSTRUCTIONMODE") or "",
            "reserved": x.get("HASACTIVERESERVEDSEATS") == "Y", "consent": x.get("CONSENT") == "Y",
            "assoc": str(x.get("ASSOCIATEDCLASS") or ""), "optional": x.get("OPTIONALSECTION") == "Y",
            "deadline": (x.get("ENROLLDEADLINE") or "")[:10] or None,
        }
    except (KeyError, TypeError) as e:
        raise Fail(4, "ASU's response has a different shape than expected (%s)" % e)
    return sec


def normalize_row(r):
    """Generic rows Cubbie read from another school's class search page (see SKILL.md)."""
    return {
        "term": str(r.get("term", "")), "subject": r.get("subject", ""), "number": str(r.get("number", "")),
        "class_nbr": str(r["class_nbr"]), "section": str(r.get("section", "")), "comp": r.get("comp", ""),
        "title": r.get("title", ""), "status": r.get("status") or ("C" if to_int(r.get("enrl")) >= to_int(r.get("cap"), 1) else "O"),
        "enrl": to_int(r.get("enrl")), "cap": to_int(r.get("cap")), "days": parse_days(r.get("days")),
        "start": parse_time(r.get("start")), "end": parse_time(r.get("end")), "mode": r.get("mode", ""),
        "reserved": bool(r.get("reserved")), "consent": bool(r.get("consent")),
        "assoc": str(r.get("assoc", "")), "optional": bool(r.get("optional")), "deadline": r.get("deadline"),
    }


def seats(sec):
    return max(sec["cap"] - sec["enrl"], 0)


def is_open(sec):
    return seats(sec) > 0 and sec["status"] != "C"


# ---------- fetching ----------

def fetch_asu_course(term, subject, number):
    params = {"refine": "Y", "campusOrOnlineSelection": "A", "subject": subject.upper(),
              "catalogNbr": number, "term": term, "advanced": "true"}
    url = API + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=15) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise Fail(3, "ASU class data returned HTTP %s" % e.code)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise Fail(3, "ASU class data is not reachable (%s)" % getattr(e, "reason", e))
    if not isinstance(data, dict) or "classes" not in data:
        raise Fail(4, "ASU's response has no 'classes' list")
    return [normalize_asu(c) for c in data["classes"]]


def load_snapshot(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return [normalize_asu(c) for c in json.load(f)["classes"]]


# ---------- pairing and conflicts ----------

def partners(sec, all_secs):
    """Linked sections that must also have a seat (lecture <-> lab/recitation)."""
    if not sec["assoc"]:
        return []
    group = [s for s in all_secs if s["class_nbr"] != sec["class_nbr"] and s["assoc"] == sec["assoc"]
             and not s["optional"]]
    primary = sec["section"] == sec["assoc"]
    return [s for s in group if (s["section"] != s["assoc"]) == primary]


def enrollable(sec, all_secs):
    if not is_open(sec):
        return False, None, []
    ps = partners(sec, all_secs)
    if not ps:
        return True, None, []
    open_ps = sorted([p for p in ps if is_open(p)], key=lambda p: -seats(p))
    return (bool(open_ps), open_ps[0] if open_ps else None, open_ps[:3])


def overlaps(sec, busy):
    if not sec["days"] or sec["start"] is None or sec["end"] is None:
        return None
    hits = []
    for b in busy:
        bd, bs, be = parse_days(b.get("days")), parse_time(b.get("start")), parse_time(b.get("end"))
        if not bd or bs is None or be is None:
            continue
        if set(bd) & set(sec["days"]) and bs < sec["end"] and sec["start"] < be:
            hits.append(b.get("title", "a commitment"))
    return hits


# ---------- state ----------

def state_path():
    return os.environ.get("SEAT_WATCH_STATE") or os.path.join(
        os.path.expanduser("~"), ".config", "seat-watch", "state.json")


def load_state():
    try:
        with open(state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"watches": []}


def save_state(st):
    p = state_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)


# ---------- commands ----------

def describe(sec):
    return "%s %s sec %s (%s %s) %s, %d/%d, %s" % (
        sec["subject"], sec["number"], sec["section"], sec["comp"] or "class", sec["class_nbr"],
        fmt_when(sec), sec["enrl"], sec["cap"], "OPEN %d left" % seats(sec) if is_open(sec) else "closed")


def cmd_lookup(a):
    secs = fetch_asu_course(a.term, a.subject, a.number)
    if not secs:
        raise Fail(6, "No sections found for %s %s in term %s" % (a.subject.upper(), a.number, a.term))
    rows = sorted(secs, key=lambda s: (s["assoc"], s["section"]))
    if a.comp:
        rows = [s for s in rows if s["comp"].upper() == a.comp.upper()]
    if a.status == "open":
        rows = [s for s in rows if is_open(s)]
    elif a.status == "closed":
        rows = [s for s in rows if not is_open(s)]
    for s in rows[:a.limit]:
        flags = [f for f, on in (("reserved seats", s["reserved"]), ("instructor consent", s["consent"])) if on]
        print("%s | %s | %s | %s | %s%s" % (
            s["class_nbr"], "%s sec %s" % (s["comp"], s["section"]), fmt_when(s),
            "%d of %d taken" % (s["enrl"], s["cap"]), "OPEN" if is_open(s) else "CLOSED",
            " | " + ", ".join(flags) if flags else ""))
    if len(rows) > a.limit:
        print("... %d more not shown; narrow with --comp LEC|REC|LAB or --status open|closed" % (len(rows) - a.limit))
    return 0


def cmd_watch(a):
    st = load_state()
    if a.action == "list":
        if not st["watches"]:
            print("Nothing is being watched.")
        for w in st["watches"]:
            print("%s | %s | %s %s | %s | role=%s" % (w["class_nbr"], w.get("label") or "", w["subject"], w["number"],
                                                     w["school"], w["role"]))
        return 0
    if a.action == "remove":
        n = len(st["watches"])
        st["watches"] = [w for w in st["watches"] if w["class_nbr"] != a.cls]
        save_state(st)
        print("Removed." if len(st["watches"]) < n else "That class number was not being watched.")
        return 0
    # add
    if len(st["watches"]) >= MAX_WATCHES:
        raise Fail(2, "Already watching %d sections; remove one first" % MAX_WATCHES)
    if any(w["class_nbr"] == a.cls for w in st["watches"]):
        print("Already watching %s." % a.cls)
        return 0
    w = {"class_nbr": a.cls, "term": a.term, "subject": (a.subject or "").upper(), "number": a.number or "",
         "school": a.school, "label": a.label or "", "role": a.role, "last_enrollable": None}
    if a.school == "asu":
        if not (a.subject and a.number):
            raise Fail(2, "--subject and --number are required for ASU")
        secs = fetch_asu_course(a.term, a.subject, a.number)
        sec = next((s for s in secs if s["class_nbr"] == a.cls), None)
        if not sec:
            raise Fail(6, "Class number %s was not found in %s %s" % (a.cls, a.subject.upper(), a.number))
        ok, _, _ = enrollable(sec, secs)
        w["last_enrollable"] = ok
        w["label"] = w["label"] or describe(sec)
        print("Watching: " + describe(sec))
        if ok:
            print("NOTE: this section is already enrollable right now.")
    else:
        print("Watching %s (%s). The first check sets the baseline." % (a.cls, a.school))
    st["watches"].append(w)
    save_state(st)
    return 0


def event_for(sec, all_secs, busy, sample):
    ok, partner, open_partners = enrollable(sec, all_secs)
    ev = {"type": "SEAT_OPENED", "class_nbr": sec["class_nbr"], "course": "%s %s" % (sec["subject"], sec["number"]),
          "section": sec["section"], "when": fmt_when(sec), "seats_left": seats(sec), "simulated": sample}
    parts = ["%sSeat opened: %s %s lec/sec %s (class %s) %s, %d seat%s left." % (
        "[SIMULATED] " if sample else "", sec["subject"], sec["number"], sec["section"], sec["class_nbr"],
        fmt_when(sec), seats(sec), "" if seats(sec) == 1 else "s")]
    chosen = [sec]
    if partner is not None:
        chosen.append(partner)
        ev["needs"] = [{"class_nbr": p["class_nbr"], "comp": p["comp"], "when": fmt_when(p), "seats_left": seats(p)}
                       for p in open_partners]
        parts.append("It needs a linked %s: class %s %s, %d seat%s left%s." % (
            partner["comp"] or "section", partner["class_nbr"], fmt_when(partner), seats(partner),
            "" if seats(partner) == 1 else "s",
            " (also open: %s)" % ", ".join(p["class_nbr"] for p in open_partners[1:]) if len(open_partners) > 1 else ""))
    conflicts, skipped = [], False
    for s in chosen:
        h = overlaps(s, busy)
        if h is None:
            skipped = True
        elif h:
            conflicts += ["%s overlaps %s" % (s["class_nbr"], ", ".join(h))]
    ev["conflicts"] = conflicts
    if conflicts:
        parts.append("Conflict: " + "; ".join(conflicts) + ". Offer a SWAP, not a drop.")
    elif busy and not skipped:
        parts.append("No time conflict with the schedule given.")
    if skipped:
        parts.append("Conflict check skipped for a section with no set meeting time.")
    caveats = []
    if sec["reserved"] or (partner and partner["reserved"]):
        caveats.append("some seats are reserved, it may not be open to everyone")
    if sec["consent"] or (partner and partner["consent"]):
        caveats.append("instructor consent may be required")
    if caveats:
        parts.append("Caveat: " + "; ".join(caveats) + ".")
        ev["caveats"] = caveats
    return ev, " ".join(parts)


def check_once(a, st, busy):
    """Returns (events, summaries, changed_state)."""
    events, lines, changed = [], [], False
    today = date.today()
    cache = {}
    for w in st["watches"]:
        if w.get("school") == "asu":
            key = (w["term"], w["subject"], w["number"])
            if key not in cache:
                cache[key] = fetch_asu_course(*key)
            secs = cache[key]
        else:
            if not a.rows:
                raise Fail(2, "Watching a non-ASU school: pass --rows FILE with the sections you read")
            if "rows" not in cache:
                with open(a.rows, encoding="utf-8") as f:
                    cache["rows"] = [normalize_row(r) for r in json.load(f)]
            secs = cache["rows"]
        sec = next((s for s in secs if s["class_nbr"] == w["class_nbr"]), None)
        if not sec:
            raise Fail(6, "Class number %s was not found in the latest data" % w["class_nbr"])
        ok, _, _ = enrollable(sec, secs)
        if sec["deadline"] and sec["deadline"] < today.isoformat():
            events.append({"type": "WATCH_EXPIRED", "class_nbr": w["class_nbr"]})
            lines.append("Watch for class %s ended: its enrollment deadline (%s) has passed." % (w["class_nbr"], sec["deadline"]))
            w["expired"] = True
            changed = True
            continue
        if w["last_enrollable"] is False and ok:
            ev, line = event_for(sec, secs, busy, False)
            events.append(ev)
            lines.append(line)
        if w["last_enrollable"] != ok:
            w["last_enrollable"] = ok
            changed = True
    st["watches"] = [w for w in st["watches"] if not w.get("expired")]
    return events, lines, changed


def emit(events, lines):
    if not events:
        print("NO CHANGE")
        return 0
    print("CHANGES: %d" % len(events))
    for e in events:
        print("EVENT " + json.dumps(e))
    for l in lines:
        print("SUMMARY: " + l)
    return 10


def cmd_check(a):
    busy = []
    if a.busy:
        try:
            busy = json.load(open(a.busy, encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise Fail(2, "Cannot read --busy file (%s)" % e)
    if a.sample:  # replay two real-shape snapshots; touches no saved state
        before, after = load_snapshot("snapshot_before.json"), load_snapshot("snapshot_after.json")
        w = next(s for s in before if s["comp"] == "LEC" and s["section"] == s["assoc"])
        was, _, _ = enrollable(w, before)
        now_sec = next(s for s in after if s["class_nbr"] == w["class_nbr"])
        now, _, _ = enrollable(now_sec, after)
        print("[SIMULATED replay] baseline: %s" % describe(w))
        if not was and now:
            ev, line = event_for(now_sec, after, busy, True)
            return emit([ev], [line])
        return emit([], [])
    st = load_state()
    if not st["watches"]:
        raise Fail(5, "Nothing is being watched")
    events, lines, changed = check_once(a, st, busy)
    if changed:
        save_state(st)
    return emit(events, lines)


def cmd_loop(a):
    """Poll inside one process; exit 10 on the first change. For testing a background watcher."""
    busy = json.load(open(a.busy, encoding="utf-8")) if a.busy else []
    deadline = time.time() + a.max_minutes * 60
    while time.time() < deadline:
        st = load_state()
        if not st["watches"]:
            raise Fail(5, "Nothing is being watched")
        events, lines, changed = check_once(a, st, busy)
        if changed:
            save_state(st)
        if events:
            return emit(events, lines)
        time.sleep(a.interval)
    print("NO CHANGE (loop ended after %d minutes)" % a.max_minutes)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="seat_watch.py", description="Watch class sections for open seats.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("lookup", help="list sections of a course")
    s.add_argument("--term", required=True)
    s.add_argument("--subject", required=True)
    s.add_argument("--number", required=True)
    s.add_argument("--comp", help="only this component type: LEC, REC, LAB ...")
    s.add_argument("--status", choices=["open", "closed", "all"], default="all")
    s.add_argument("--limit", type=int, default=15, help="max rows to print (default 15)")
    s.set_defaults(fn=cmd_lookup)
    s = sub.add_parser("watch", help="add, list or remove watches")
    s.add_argument("action", choices=["add", "list", "remove"])
    s.add_argument("--class", dest="cls")
    s.add_argument("--term", default="")
    s.add_argument("--subject")
    s.add_argument("--number")
    s.add_argument("--school", default="asu")
    s.add_argument("--label")
    s.add_argument("--role", choices=["must", "backup"], default="must")
    s.set_defaults(fn=cmd_watch)
    for name, fn in (("check", cmd_check), ("loop", cmd_loop)):
        s = sub.add_parser(name, help="compare current seats with the last check" if name == "check"
                           else "poll repeatedly in one process (for testing a background watcher)")
        s.add_argument("--busy", help="JSON file of the student's busy blocks")
        s.add_argument("--rows", help="JSON rows read from a non-ASU class search page")
        if name == "check":
            s.add_argument("--sample", action="store_true", help="replay the bundled snapshots; no saved state used")
        else:
            s.add_argument("--interval", type=int, default=45)
            s.add_argument("--max-minutes", type=int, default=55)
            s.sample = False
        s.set_defaults(fn=fn)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "watch" and a.action in ("add", "remove") and not a.cls:
        print("ERROR: --class is required", file=sys.stderr)
        return 2
    if a.cmd == "loop":
        a.sample = False
    try:
        return a.fn(a)
    except Fail as e:
        print("ERROR: " + e.msg)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
