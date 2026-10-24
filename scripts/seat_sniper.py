#!/usr/bin/env python3
"""seat-sniper: watch full class sections and report when a seat or a waitlist spot opens.

Standard library only. State lives under HOME so it survives restarts and Skill updates.

One neutral section format, three ways to fill it (--source):
  asu     ASU's public class search feed
  banner  any school whose public class search is Ellucian Banner 9 (needs --host)
  rows    sections Cubbie read off any other school's class search page (JSON file)

Exit codes (SKILL.md maps each to a reply):
  0 no change (send the student nothing)    10 change printed
  2 bad arguments                           3 the school's site is unreachable or errored
  4 the data is not in the expected shape (or needs a login)
  5 nothing is being watched                6 class number not found
"""
import argparse
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

UA = "seat-sniper/0.1 (student project; low-rate, read-only)"
ASU_API = "https://eadvs-cscc-catalog-api.apps.asu.edu/catalog-microservices/api/v1/search/classes"
ASU_HEADERS = {"Authorization": "Bearer null",  # what ASU's public class-search page itself sends
               "User-Agent": UA}
DAYS = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5, "Su": 6}
BANNER_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")
MAX_WATCHES = 5
RANK = {None: 0, "wait": 1, "seat": 2}


class Fail(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


# ---------- parsing helpers ----------

def parse_days(value):
    """['M W'], ['T Th'], [''] , '&nbsp;', 'MWF' or 'M W F' -> sorted weekday numbers."""
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
    """'9:00 AM', '09:00', '1530' or None -> minutes after midnight, or None."""
    if value is None or str(value).strip() in ("", "None", "&nbsp;"):
        return None
    s = str(value).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*([AaPp][Mm])?$", s)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    elif re.match(r"^\d{4}$", s):
        h, mi, ap = int(s[:2]), int(s[2:]), None
    else:
        return None
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


def fmt_meetings(meetings):
    timed = [m for m in meetings if m["days"] and m["start"] is not None]
    if not timed:
        return "no set meeting time (online/async)"
    return "; ".join("%s %s-%s" % (fmt_days(m["days"]), fmt_time(m["start"]), fmt_time(m["end"])) for m in timed)


def to_int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def meeting(days, start, end):
    m = {"days": days, "start": parse_time(start), "end": parse_time(end)}
    return m if (m["days"] or m["start"] is not None) else None


# ---------- neutral section format ----------

def make_section(**kw):
    sec = {"source": "", "term": "", "subject": "", "number": "", "class_nbr": "", "section": "", "comp": "",
           "title": "", "status": "O", "enrl": 0, "cap": 0, "wait_cap": 0, "wait_count": 0, "meetings": [],
           "mode": "", "reserved": False, "consent": False, "link": "", "optional": False, "deadline": None}
    sec.update(kw)
    return sec


def seats(sec):
    return max(sec["cap"] - sec["enrl"], 0)


def is_open(sec):
    return seats(sec) > 0 and sec["status"] != "C"


def wait_room(sec):
    return (not is_open(sec)) and sec["wait_cap"] > 0 and sec["wait_count"] < sec["wait_cap"]


def own_kind(sec):
    return "seat" if is_open(sec) else ("wait" if wait_room(sec) else None)


def normalize_asu(c):
    try:
        x = c["CLAS"]
        days_list = c.get("DAYLIST") if isinstance(c.get("DAYLIST"), list) else [c.get("DAYLIST") or ""]
        starts, ends = c.get("STARTTIMES"), c.get("ENDTIMES")
        if isinstance(starts, list) and isinstance(ends, list) and len(starts) == len(days_list) == len(ends):
            raw = list(zip(days_list, starts, ends))
        else:
            raw = [(" ".join(days_list), x.get("STARTTIME"), x.get("ENDTIME"))]
        meetings = [m for m in (meeting(parse_days(d), s, e) for d, s, e in raw) if m]
        return make_section(
            source="asu", term=str(x["STRM"]), subject=x["SUBJECT"], number=str(x["CATALOGNBR"]),
            class_nbr=str(x["CLASSNBR"]), section=str(x["CLASSSECTION"]), comp=x.get("COMPONENTPRIMARY") or "",
            title=x.get("TITLE") or "", status=x["ENRLSTAT"], enrl=to_int(x["ENRLTOT"]), cap=to_int(x["ENRLCAP"]),
            wait_cap=to_int(x.get("WAITCAP")), wait_count=to_int(x.get("WAITTOT")), meetings=meetings,
            mode=x.get("INSTRUCTIONMODE") or "", reserved=x.get("HASACTIVERESERVEDSEATS") == "Y",
            consent=x.get("CONSENT") == "Y", link=str(x.get("ASSOCIATEDCLASS") or ""),
            optional=x.get("OPTIONALSECTION") == "Y", deadline=(x.get("ENROLLDEADLINE") or "")[:10] or None)
    except (KeyError, TypeError) as e:
        raise Fail(4, "ASU's response has a different shape than expected (%s)" % e)


def normalize_banner(r, host):
    try:
        meetings = []
        for mf in r.get("meetingsFaculty") or []:
            mt = mf.get("meetingTime") or {}
            m = meeting([i for i, k in enumerate(BANNER_DAYS) if mt.get(k)], mt.get("beginTime"), mt.get("endTime"))
            if m:
                meetings.append(m)
        return make_section(
            source="banner:" + host, term=str(r["term"]), subject=r["subject"], number=str(r["courseNumber"]),
            class_nbr=str(r["courseReferenceNumber"]), section=str(r.get("sequenceNumber") or ""),
            comp=r.get("scheduleTypeDescription") or "", title=r.get("courseTitle") or "",
            status="O" if r["openSection"] else "C", enrl=to_int(r["enrollment"]), cap=to_int(r["maximumEnrollment"]),
            wait_cap=to_int(r.get("waitCapacity")), wait_count=to_int(r.get("waitCount")), meetings=meetings,
            mode=r.get("instructionalMethodDescription") or "", reserved=bool(r.get("reservedSeatSummary")),
            link=str(r.get("linkIdentifier") or ""))
    except (KeyError, TypeError) as e:
        raise Fail(4, "This school's class search has a different shape than Banner 9 (%s)" % e)


def normalize_row(r):
    """Rows Cubbie read from any other school's class search page (see references/other-schools.md)."""
    if "meetings" in r:
        meetings = [m for m in (meeting(parse_days(x.get("days")), x.get("start"), x.get("end")) for x in r["meetings"]) if m]
    else:
        m = meeting(parse_days(r.get("days")), r.get("start"), r.get("end"))
        meetings = [m] if m else []
    enrl, cap = to_int(r.get("enrl")), to_int(r.get("cap"))
    return make_section(
        source="rows", term=str(r.get("term", "")), subject=r.get("subject", ""), number=str(r.get("number", "")),
        class_nbr=str(r["class_nbr"]), section=str(r.get("section", "")), comp=r.get("comp", ""),
        title=r.get("title", ""), status=r.get("status") or ("C" if cap and enrl >= cap else "O"), enrl=enrl, cap=cap,
        wait_cap=to_int(r.get("wait_cap")), wait_count=to_int(r.get("wait_count")), meetings=meetings,
        mode=r.get("mode", ""), reserved=bool(r.get("reserved")), consent=bool(r.get("consent")),
        link=str(r.get("link") or r.get("assoc") or ""), optional=bool(r.get("optional")), deadline=r.get("deadline"))


# ---------- fetching ----------

def fetch_asu(term, subject, number):
    params = {"refine": "Y", "campusOrOnlineSelection": "A", "subject": subject.upper(), "term": term, "advanced": "true"}
    if number:
        params["catalogNbr"] = number
    try:
        with urllib.request.urlopen(urllib.request.Request(ASU_API + "?" + urllib.parse.urlencode(params),
                                                           headers=ASU_HEADERS), timeout=15) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise Fail(3, "ASU class data returned HTTP %s" % e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Fail(3, "ASU class data is not reachable (%s)" % getattr(e, "reason", e))
    except json.JSONDecodeError:
        raise Fail(4, "ASU class data did not return JSON")
    if not isinstance(data, dict) or "classes" not in data:
        raise Fail(4, "ASU's response has no 'classes' list")
    return [normalize_asu(c) for c in data["classes"]]


_banner = {}


def banner_session(host, term):
    key = (host, term)
    if key not in _banner:
        base = "https://%s/StudentRegistrationSsb/ssb/" % host
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        op.addheaders = [("User-Agent", UA)]
        form = urllib.parse.urlencode({"term": term, "studyPath": "", "studyPathText": "",
                                       "startDatepicker": "", "endDatepicker": ""}).encode()
        try:
            op.open(base + "classSearch/classSearch", timeout=20).read()
            op.open(urllib.request.Request(base + "term/search?mode=search", data=form), timeout=20).read()
        except urllib.error.HTTPError as e:
            raise Fail(3, "%s returned HTTP %s" % (host, e.code))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise Fail(3, "%s is not reachable (%s)" % (host, getattr(e, "reason", e)))
        _banner[key] = (op, base)
    return _banner[key]


def fetch_banner(host, term, subject, number):
    op, base = banner_session(host, term)
    out, offset = [], 0
    while True:
        q = {"txt_subject": subject.upper(), "txt_term": term, "startDatepicker": "", "endDatepicker": "",
             "pageOffset": offset, "pageMaxSize": 200, "sortColumn": "subjectDescription", "sortDirection": "asc"}
        if number:
            q["txt_courseNumber"] = number
        try:
            with op.open(base + "searchResults/searchResults?" + urllib.parse.urlencode(q), timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise Fail(3, "%s returned HTTP %s" % (host, e.code))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise Fail(3, "%s is not reachable (%s)" % (host, getattr(e, "reason", e)))
        except json.JSONDecodeError:
            raise Fail(4, "%s did not return class data (it may need a login, or is not Banner 9)" % host)
        if not isinstance(data, dict) or not data.get("success"):
            raise Fail(4, "%s did not accept that term or search" % host)
        rows = data.get("data") or []
        out += rows
        offset += 200
        if offset >= to_int(data.get("totalCount")) or offset >= 1000 or not rows:
            break
        time.sleep(1)
    return [normalize_banner(r, host) for r in out]


def fetch_course(source, term, subject, number, rows_file=None):
    kind = source["source"]
    if kind == "asu":
        return fetch_asu(term, subject, number)
    if kind == "banner":
        return fetch_banner(source["host"], term, subject, number)
    if not rows_file:
        raise Fail(2, "This school is read from a rows file: pass --rows FILE with the sections you read")
    try:
        with open(rows_file, encoding="utf-8") as f:
            return [normalize_row(r) for r in json.load(f)]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise Fail(2, "Cannot read the rows file (%s)" % e)


def load_snapshot(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return [normalize_asu(c) for c in json.load(f)["classes"]]


# ---------- availability, linked sections, conflicts ----------

def evaluate(sec, all_secs):
    """-> (kind, chosen_partners). kind is 'seat', 'wait' or None, the worst of the section itself and every
    linked component (lab, recitation...) the student must also get."""
    kind, chosen = own_kind(sec), []
    if sec["link"]:
        groups = {}
        for s in all_secs:
            if (s["class_nbr"] != sec["class_nbr"] and s["link"] == sec["link"] and not s["optional"]
                    and s["subject"] == sec["subject"] and s["number"] == sec["number"] and s["comp"] != sec["comp"]):
                groups.setdefault(s["comp"], []).append(s)
        for comp, members in groups.items():
            best = max(members, key=lambda s: (RANK[own_kind(s)], seats(s)))
            chosen.append(best)
            if RANK[own_kind(best)] < RANK[kind]:
                kind = own_kind(best)
    return kind, chosen


def overlaps(sec, busy):
    """Names of busy blocks that overlap any meeting of sec; None when sec has no meeting time to compare."""
    timed = [m for m in sec["meetings"] if m["days"] and m["start"] is not None and m["end"] is not None]
    if not timed:
        return None
    hits = []
    for b in busy:
        bd, bs, be = parse_days(b.get("days")), parse_time(b.get("start")), parse_time(b.get("end"))
        if not bd or bs is None or be is None:
            continue
        for m in timed:
            if set(bd) & set(m["days"]) and bs < m["end"] and m["start"] < be:
                hits.append(b.get("title", "a commitment"))
                break
    return hits


# ---------- state ----------

def state_path():
    return os.environ.get("SEAT_SNIPER_STATE") or os.path.join(
        os.path.expanduser("~"), ".config", "seat-sniper", "state.json")


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


def source_from_args(a):
    if a.source == "banner":
        if not a.host:
            raise Fail(2, "--host is required for --source banner (the school's registration host, e.g. reg.school.edu)")
        return {"source": "banner", "host": a.host}
    if a.source == "rows":
        return {"source": "rows", "school": a.school or "other"}
    return {"source": "asu"}


# ---------- text ----------

def course_name(sec):
    return ("%s %s" % (sec["subject"], sec["number"])).strip() or "class"


def status_line(sec):
    if is_open(sec):
        return "open, %d seat%s left (%d/%d taken)" % (seats(sec), "" if seats(sec) == 1 else "s", sec["enrl"], sec["cap"])
    if wait_room(sec):
        return "full (%d/%d), waitlist has room (%d of %d taken)" % (sec["enrl"], sec["cap"], sec["wait_count"], sec["wait_cap"])
    if sec["wait_cap"] > 0:
        return "full (%d/%d), waitlist is full" % (sec["enrl"], sec["cap"])
    return "full (%d/%d), no waitlist" % (sec["enrl"], sec["cap"])


def describe(sec):
    return "%s sec %s (%s %s) %s, %s" % (course_name(sec), sec["section"], sec["comp"] or "class", sec["class_nbr"],
                                         fmt_meetings(sec["meetings"]), status_line(sec))


def build_event(etype, sec, kind, partners, busy, sample, extra=None):
    ev = {"type": etype, "class_nbr": sec["class_nbr"], "course": course_name(sec), "section": sec["section"],
          "when": fmt_meetings(sec["meetings"]), "simulated": sample}
    tag = "[SIMULATED] " if sample else ""
    if etype == "SEAT_OPENED":
        parts = ["%sSeat opened: %s sec %s (class %s) %s, %d seat%s left." % (
            tag, course_name(sec), sec["section"], sec["class_nbr"], fmt_meetings(sec["meetings"]), seats(sec),
            "" if seats(sec) == 1 else "s")]
    elif etype == "WAITLIST_OPENED":
        parts = ["%sWaitlist spot opened (not a seat yet): %s sec %s (class %s) %s. Waitlist: %d of %d taken." % (
            tag, course_name(sec), sec["section"], sec["class_nbr"], fmt_meetings(sec["meetings"]),
            sec["wait_count"], sec["wait_cap"])]
    else:  # WAITLIST_MOVED
        parts = ["%sWaitlist moved: %s sec %s (class %s) waitlist went from %d to %d people. Still no seat." % (
            tag, course_name(sec), sec["section"], sec["class_nbr"], extra["was"], sec["wait_count"])]
        ev.update(waitlist_was=extra["was"], waitlist_now=sec["wait_count"])
        return ev, " ".join(parts)
    ev["seats_left"] = seats(sec)
    chosen = [sec] + partners
    if partners:
        ev["needs"] = [{"class_nbr": p["class_nbr"], "comp": p["comp"], "when": fmt_meetings(p["meetings"]),
                        "state": own_kind(p)} for p in partners]
        for p in partners:
            parts.append("It also needs a linked %s: class %s %s, %s." % (
                p["comp"] or "section", p["class_nbr"], fmt_meetings(p["meetings"]), status_line(p)))
    conflicts, skipped = [], False
    for s in chosen:
        h = overlaps(s, busy)
        if h is None:
            skipped = True
        elif h:
            conflicts.append("class %s overlaps %s" % (s["class_nbr"], ", ".join(h)))
    ev["conflicts"] = conflicts
    if conflicts:
        parts.append("Conflict: " + "; ".join(conflicts) + ". If the school has a swap, offer a swap; never drop first.")
    elif busy and not skipped:
        parts.append("No time conflict with the schedule given.")
    if skipped:
        parts.append("Conflict check skipped for a section with no set meeting time.")
    caveats = []
    if any(s["reserved"] for s in chosen):
        caveats.append("some seats are reserved, it may not be open to everyone")
    if any(s["consent"] for s in chosen):
        caveats.append("instructor consent may be required")
    if caveats:
        parts.append("Caveat: " + "; ".join(caveats) + ".")
        ev["caveats"] = caveats
    return ev, " ".join(parts)


def decide(w, sec, all_secs, busy, sample=False):
    """Compare one watch with fresh data. Updates w. Returns (events, summary lines)."""
    kind, partners = evaluate(sec, all_secs)
    events, lines = [], []
    last, last_wait = w.get("last_kind", "unset"), w.get("last_wait")
    if last != "unset":
        if kind == "seat" and last != "seat":
            ev, line = build_event("SEAT_OPENED", sec, kind, partners, busy, sample)
            events.append(ev), lines.append(line)
        elif kind == "wait" and last is None:
            ev, line = build_event("WAITLIST_OPENED", sec, kind, partners, busy, sample)
            events.append(ev), lines.append(line)
        elif (not is_open(sec) and sec["wait_cap"] > 0 and last_wait is not None
              and sec["wait_count"] < last_wait):
            ev, line = build_event("WAITLIST_MOVED", sec, kind, partners, busy, sample, {"was": last_wait})
            events.append(ev), lines.append(line)
    w["last_kind"], w["last_wait"] = kind, sec["wait_count"]
    return events, lines


# ---------- commands ----------

def cmd_terms(a):
    if a.source == "banner":
        if not a.host:
            raise Fail(2, "--host is required")
        url = "https://%s/StudentRegistrationSsb/ssb/classSearch/getTerms?searchTerm=&offset=1&max=10" % a.host
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20) as r:
                for t in json.load(r):
                    print("%s | %s" % (t["code"], t["description"]))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise Fail(3, "%s is not reachable (%s)" % (a.host, getattr(e, "reason", e)))
        except (json.JSONDecodeError, KeyError, TypeError):
            raise Fail(4, "%s did not return a term list" % a.host)
    elif a.source == "asu":
        print("ASU term codes follow 2<yy><d>: d is 1 spring, 4 summer, 7 fall (2271 = Spring 2027). "
              "Confirm with a lookup that returns sections.")
    else:
        print("Take the term from the school's class search page.")
    return 0


def cmd_lookup(a):
    secs = fetch_course(source_from_args(a), a.term, a.subject, a.number or "", a.rows)
    secs = [s for s in secs if s["subject"].upper() == a.subject.upper() or a.source == "rows"]
    if a.number:
        secs = [s for s in secs if s["number"] == str(a.number) or a.source == "rows"]
    if not secs:
        raise Fail(6, "No sections found for %s %s in term %s" % (a.subject.upper(), a.number or "", a.term))
    rows = sorted(secs, key=lambda s: (s["number"], s["link"], s["section"]))
    if a.comp:
        rows = [s for s in rows if s["comp"].upper() == a.comp.upper()]
    if a.status == "open":
        rows = [s for s in rows if is_open(s)]
    elif a.status == "closed":
        rows = [s for s in rows if not is_open(s)]
    for s in rows[:a.limit]:
        flags = [f for f, on in (("reserved seats", s["reserved"]), ("instructor consent", s["consent"])) if on]
        print("%s | %s %s sec %s %s | %s | %s%s" % (
            s["class_nbr"], course_name(s), s["comp"], s["section"], "", fmt_meetings(s["meetings"]), status_line(s),
            " | " + ", ".join(flags) if flags else ""))
    if len(rows) > a.limit:
        print("... %d more not shown; narrow with --number, --comp or --status open|closed" % (len(rows) - a.limit))
    return 0


def cmd_watch(a):
    st = load_state()
    if a.action == "list":
        if not st["watches"]:
            print("Nothing is being watched.")
        for w in st["watches"]:
            print("%s | %s | %s | %s | role=%s" % (w["class_nbr"], w.get("label") or "", w["subject"] + " " + w["number"],
                                                   w["source"].get("host") or w["source"]["source"], w["role"]))
        return 0
    if a.action == "remove":
        n = len(st["watches"])
        st["watches"] = [w for w in st["watches"] if w["class_nbr"] != a.cls]
        save_state(st)
        print("Removed." if len(st["watches"]) < n else "That class number was not being watched.")
        return 0
    if len(st["watches"]) >= MAX_WATCHES:
        raise Fail(2, "Already watching %d sections; remove one first" % MAX_WATCHES)
    if any(w["class_nbr"] == a.cls for w in st["watches"]):
        print("Already watching %s." % a.cls)
        return 0
    if not (a.subject and a.number and a.term):
        raise Fail(2, "--term, --subject and --number are required")
    source = source_from_args(a)
    w = {"class_nbr": a.cls, "term": a.term, "subject": a.subject.upper(), "number": a.number, "source": source,
         "label": a.label or "", "role": a.role, "last_kind": "unset", "last_wait": None}
    if source["source"] == "rows" and not a.rows:
        print("Watching %s. The first check sets the baseline." % a.cls)
    else:
        secs = fetch_course(source, a.term, a.subject, a.number, a.rows)
        sec = next((s for s in secs if s["class_nbr"] == a.cls), None)
        if not sec:
            raise Fail(6, "Class number %s was not found in %s %s" % (a.cls, a.subject.upper(), a.number))
        w["last_kind"], w["last_wait"] = evaluate(sec, secs)[0], sec["wait_count"]
        w["label"] = w["label"] or describe(sec)
        print("Watching: " + describe(sec))
        if w["last_kind"] == "seat":
            print("NOTE: this section is already enrollable right now.")
        elif w["last_kind"] == "wait":
            print("NOTE: no seat, but the waitlist has room, so the student can join it now.")
    st["watches"].append(w)
    save_state(st)
    return 0


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


def load_busy(path):
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise Fail(2, "Cannot read --busy file (%s)" % e)


def check_once(a, st, busy):
    events, lines, changed, cache = [], [], False, {}
    today = date.today().isoformat()
    keep = []
    for w in st["watches"]:
        key = (json.dumps(w["source"], sort_keys=True), w["term"], w["subject"], w["number"])
        if key not in cache:
            cache[key] = fetch_course(w["source"], w["term"], w["subject"], w["number"], getattr(a, "rows", None))
        secs = cache[key]
        sec = next((s for s in secs if s["class_nbr"] == w["class_nbr"]), None)
        if not sec:
            events.append({"type": "SECTION_MISSING", "class_nbr": w["class_nbr"]})
            lines.append("Class %s is no longer in the school's class data (it may have been cancelled). Watch removed." % w["class_nbr"])
            changed = True
            continue
        if sec["deadline"] and sec["deadline"] < today:
            events.append({"type": "WATCH_EXPIRED", "class_nbr": w["class_nbr"]})
            lines.append("Watch for class %s ended: its enrollment deadline (%s) has passed." % (w["class_nbr"], sec["deadline"]))
            changed = True
            continue
        before = (w["last_kind"], w["last_wait"])
        ev, ln = decide(w, sec, secs, busy)
        events += ev
        lines += ln
        changed = changed or before != (w["last_kind"], w["last_wait"])
        keep.append(w)
    st["watches"] = keep
    return events, lines, changed


def cmd_check(a):
    busy = load_busy(a.busy)
    if a.sample:  # replay two real-shape snapshots; touches no saved state
        before, after = load_snapshot("snapshot_before.json"), load_snapshot("snapshot_after.json")
        target = next(s for s in before if s["link"] and own_kind(s) is None and s["comp"] == "LEC")
        sec_after = next(s for s in after if s["class_nbr"] == target["class_nbr"])
        w = {"last_kind": evaluate(target, before)[0], "last_wait": target["wait_count"]}
        print("[SIMULATED replay] baseline: " + describe(target))
        ev, ln = decide(w, sec_after, after, busy, sample=True)
        return emit(ev, ln)
    st = load_state()
    if not st["watches"]:
        raise Fail(5, "Nothing is being watched")
    events, lines, changed = check_once(a, st, busy)
    if changed:
        save_state(st)
    return emit(events, lines)


def cmd_loop(a):
    """Poll inside one process; exit 10 on the first change. For testing a background watcher."""
    busy = load_busy(a.busy)
    end = time.time() + a.max_minutes * 60
    while time.time() < end:
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


def add_source_args(s, required):
    s.add_argument("--source", choices=["asu", "banner", "rows"], required=required,
                   help="where seat data comes from")
    s.add_argument("--host", help="banner: the school's registration host, e.g. reg.school.edu")
    s.add_argument("--school", help="rows: a label for the school")
    s.add_argument("--rows", help="rows: JSON file of sections read from the school's class search page")


def build_parser():
    p = argparse.ArgumentParser(prog="seat_sniper.py", description="Watch class sections for open seats and waitlist spots.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("terms", help="list a school's term codes")
    add_source_args(s, True)
    s.set_defaults(fn=cmd_terms)
    s = sub.add_parser("lookup", help="list sections of a subject or course")
    add_source_args(s, True)
    s.add_argument("--term", required=True)
    s.add_argument("--subject", required=True)
    s.add_argument("--number", help="course number; leave out to list the whole subject")
    s.add_argument("--comp", help="only this component type: Lecture, LEC, LAB ...")
    s.add_argument("--status", choices=["open", "closed", "all"], default="all")
    s.add_argument("--limit", type=int, default=15, help="max rows to print (default 15)")
    s.set_defaults(fn=cmd_lookup)
    s = sub.add_parser("watch", help="add, list or remove watches")
    s.add_argument("action", choices=["add", "list", "remove"])
    add_source_args(s, False)
    s.add_argument("--class", dest="cls", help="the section's class number (CRN)")
    s.add_argument("--term")
    s.add_argument("--subject")
    s.add_argument("--number")
    s.add_argument("--label")
    s.add_argument("--role", choices=["must", "backup"], default="must")
    s.set_defaults(fn=cmd_watch)
    for name, fn in (("check", cmd_check), ("loop", cmd_loop)):
        s = sub.add_parser(name, help="compare current seats with the last check" if name == "check"
                           else "poll repeatedly in one process (for testing a background watcher)")
        s.add_argument("--busy", help="JSON file of the student's busy blocks")
        s.add_argument("--rows", help="JSON rows read from a school's class search page (rows source)")
        if name == "check":
            s.add_argument("--sample", action="store_true", help="replay the bundled snapshots; no saved state used")
        else:
            s.add_argument("--interval", type=int, default=45)
            s.add_argument("--max-minutes", type=int, default=55)
        s.set_defaults(fn=fn)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "watch" and a.action in ("add", "remove") and not a.cls:
        print("ERROR: --class is required")
        return 2
    if a.cmd == "watch" and a.action == "add" and not a.source:
        print("ERROR: --source is required")
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
