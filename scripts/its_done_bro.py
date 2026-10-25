#!/usr/bin/env python3
"""its-done-bro: watch class sections and report when a seat you can actually take opens.

Standard library only. State lives under HOME so it survives restarts and Skill updates.
A seat only counts if the section is open, every linked lab/recitation can also be taken,
and (when the student's schedule is passed with --busy) nothing overlaps.

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
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

UA = "its-done-bro/0.2 (student project; low-rate, read-only)"
ASU_API = "https://eadvs-cscc-catalog-api.apps.asu.edu/catalog-microservices/api/v1/search/classes"
ASU_HEADERS = {"Authorization": "Bearer null",  # what ASU's public class-search page itself sends
               "User-Agent": UA}
DAYS = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5, "Su": 6}
BANNER_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MAX_WATCHES = 10
MAX_ERRORS = 3
EXPIRE_DAYS = 30
FOLLOW_UP_MINUTES = 5
DEFAULT_PREFS = {"calls_ok": None, "quiet_start": "22:00", "quiet_end": "07:30"}


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
           "title": "", "status": "O", "enrl": 0, "cap": 0, "meetings": [], "mode": "", "campus": "",
           "instructors": [], "reserved": False, "consent": False, "link": "", "optional": False, "deadline": None}
    sec.update(kw)
    return sec


def seats(sec):
    return max(sec["cap"] - sec["enrl"], 0)


def is_open(sec):
    return seats(sec) > 0 and sec["status"] != "C"


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
            meetings=meetings, mode=x.get("INSTRUCTIONMODE") or "", campus=x.get("CAMPUS") or "",
            instructors=[n for n in (x.get("INSTRUCTORSLIST") or []) if n],
            reserved=x.get("HASACTIVERESERVEDSEATS") == "Y", consent=x.get("CONSENT") == "Y",
            link=str(x.get("ASSOCIATEDCLASS") or ""), optional=x.get("OPTIONALSECTION") == "Y",
            deadline=(x.get("ENROLLDEADLINE") or "")[:10] or None)
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
            meetings=meetings, mode=r.get("instructionalMethodDescription") or "",
            campus=r.get("campusDescription") or "",
            instructors=[f.get("displayName") for f in (r.get("faculty") or []) if f.get("displayName")],
            reserved=bool(r.get("reservedSeatSummary")), link=str(r.get("linkIdentifier") or ""))
    except (KeyError, TypeError) as e:
        raise Fail(4, "This school's class search has a different shape than Banner 9 (%s)" % e)


def normalize_row(r):
    """Rows Cubbie read from any other school's class search page (format in SKILL.md)."""
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
        meetings=meetings, mode=r.get("mode", ""), campus=r.get("campus", ""), instructors=list(r.get("instructors") or []),
        reserved=bool(r.get("reserved")), consent=bool(r.get("consent")),
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


def registration_link(source, term, sec):
    """A deep link where the school has one; otherwise None and Cubbie looks up the school's registration page."""
    if source["source"] == "asu":
        return "https://go.oasis.asu.edu/addclass/?STRM=%s&ASU_CLASS_NBR=%s" % (term, sec["class_nbr"])
    return None


# ---------- can the student actually take it? ----------

def own_open(sec):
    return is_open(sec)


def required_partners(sec, all_secs):
    """For each other component type linked to this section (lab, recitation...), the best open option, or any one."""
    if not sec["link"]:
        return []
    groups = {}
    for s in all_secs:
        if (s["class_nbr"] != sec["class_nbr"] and s["link"] == sec["link"] and not s["optional"]
                and s["subject"] == sec["subject"] and s["number"] == sec["number"] and s["comp"] != sec["comp"]):
            groups.setdefault(s["comp"], []).append(s)
    return [max(members, key=lambda s: (is_open(s), seats(s))) for members in groups.values()]


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


def assess(sec, all_secs, busy):
    """Decide whether this section is usable for the student right now."""
    partners = required_partners(sec, all_secs)
    chosen = [sec] + partners
    a = {"sec": sec, "partners": partners, "open": is_open(sec), "usable": False, "reason": None,
         "conflicts": [], "skipped_check": False, "caveats": []}
    if not a["open"]:
        a["reason"] = "full"
        return a
    full = [p for p in partners if not is_open(p)]
    if full:
        a["reason"] = "required %s is full" % (full[0]["comp"] or "linked section")
    for s in chosen:
        h = overlaps(s, busy)
        if h is None:
            a["skipped_check"] = True
        elif h:
            a["conflicts"].append("class %s overlaps %s" % (s["class_nbr"], ", ".join(h)))
    if a["conflicts"] and not a["reason"]:
        a["reason"] = a["conflicts"][0]
    if any(s["reserved"] for s in chosen):
        a["caveats"].append("some seats are reserved, it may not be open to everyone")
    if any(s["consent"] for s in chosen):
        a["caveats"].append("instructor consent may be required")
    a["usable"] = a["reason"] is None
    return a


def is_lecture(sec):
    return sec["comp"].upper() in ("LEC", "LECTURE")


def is_online(sec):
    return sec["mode"].upper() in ("OL", "ONLINE") or "online" in sec["mode"].lower() or sec["campus"].upper() == "ICOURSE"


def matches(sec, f):
    if f.get("instructor") and not any(f["instructor"].lower() in n.lower() for n in sec["instructors"]):
        return False
    if f.get("campus") and f["campus"].lower() not in sec["campus"].lower():
        return False
    if f.get("online") and not is_online(sec):
        return False
    if f.get("comp") and sec["comp"].upper() != f["comp"].upper():
        return False
    return True


def candidates(w, secs):
    """The sections a watch is about: one class number, or every matching primary section of the course."""
    if w.get("class_nbr"):
        return [s for s in secs if s["class_nbr"] == w["class_nbr"]]
    pool = [s for s in secs if s["subject"].upper() == w["subject"] and s["number"] == str(w["number"])]
    f = w.get("filters") or {}
    pool = [s for s in pool if matches(s, f)]
    if not f.get("comp") and any(is_lecture(s) for s in pool):
        pool = [s for s in pool if is_lecture(s)]
    return pool


def backups_for(w, secs, busy, exclude):
    """Other usable sections of the same course that satisfy the watch's filters."""
    f = dict(w.get("filters") or {})
    pool = [s for s in secs if s["subject"].upper() == w["subject"] and s["number"] == str(w["number"])
            and s["class_nbr"] not in exclude and matches(s, f)]
    if not f.get("comp") and any(is_lecture(s) for s in pool):
        pool = [s for s in pool if is_lecture(s)]
    out = [a for a in (assess(s, secs, busy) for s in pool) if a["usable"]]
    return sorted(out, key=lambda a: -seats(a["sec"]))[:3]


# ---------- state ----------

def state_path():
    return os.environ.get("ITS_DONE_BRO_STATE") or os.path.join(
        os.path.expanduser("~"), ".config", "its-done-bro", "state.json")


def load_state():
    p = state_path()
    st = {}
    try:
        with open(p, encoding="utf-8") as f:
            st = json.load(f)
        if not isinstance(st, dict) or not isinstance(st.get("watches"), list):
            raise ValueError("bad shape")
    except FileNotFoundError:
        st = {}
    except (ValueError, OSError):
        # never silently drop a student's watches: keep the damaged file aside
        try:
            os.replace(p, p + ".corrupt-" + datetime.now().strftime("%Y%m%d%H%M%S"))
        except OSError:
            pass
        print("WARN: the saved watches were unreadable and were set aside; start fresh with watch add")
        st = {}
    st.setdefault("next_id", 1)
    st.setdefault("watches", [])
    st["prefs"] = dict(DEFAULT_PREFS, **(st.get("prefs") or {}))
    return st


def save_state(st):
    p = state_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, p)


def parse_now(s):
    if not s:
        return datetime.now().replace(second=0, microsecond=0)
    try:
        return datetime.fromisoformat(s.strip().replace(" ", "T")).replace(tzinfo=None)
    except ValueError:
        raise Fail(2, "--now must look like 2026-10-24T16:30 (the student's local time)")


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")


def in_quiet(now, prefs):
    s, e, t = prefs["quiet_start"], prefs["quiet_end"], now.strftime("%H:%M")
    return (s <= t < e) if s <= e else (t >= s or t < e)


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
    return "full (%d/%d)" % (sec["enrl"], sec["cap"])


def describe(sec):
    who = (" (" + sec["instructors"][0] + ")") if sec["instructors"] else ""
    return "%s sec %s%s (%s %s) %s, %s" % (course_name(sec), sec["section"], who, sec["comp"] or "class",
                                           sec["class_nbr"], fmt_meetings(sec["meetings"]), status_line(sec))


def seat_event(w, a, others, blocked, backups, prefs, now):
    sec = a["sec"]
    link = registration_link(w["source"], w["term"], sec)
    quiet = in_quiet(now, prefs)
    call = "yes" if prefs.get("calls_ok") and not quiet else "no"
    ev = {"type": "SEAT_OPENED", "watch": w["id"], "class_nbr": sec["class_nbr"], "course": course_name(sec),
          "section": sec["section"], "when": fmt_meetings(sec["meetings"]), "seats_left": seats(sec),
          "needs": [{"class_nbr": p["class_nbr"], "comp": p["comp"], "when": fmt_meetings(p["meetings"])}
                    for p in a["partners"]],
          "link": link, "call": call, "caveats": a["caveats"],
          "also_usable": [x["sec"]["class_nbr"] for x in others],
          "blocked": [{"class_nbr": b["sec"]["class_nbr"], "section": b["sec"]["section"], "reason": b["reason"]}
                      for b in blocked]}
    if call == "yes":
        ev["follow_up_minutes"] = FOLLOW_UP_MINUTES
    if quiet and prefs.get("calls_ok"):
        ev["quiet_hours"] = True
    parts = ["Seat found: %s sec %s (class %s) %s, %d seat%s open." % (
        ev["course"], ev["section"], ev["class_nbr"], ev["when"], ev["seats_left"], "" if ev["seats_left"] == 1 else "s")]
    for p in a["partners"]:
        parts.append("Required %s open: class %s %s." % (p["comp"] or "section", p["class_nbr"], fmt_meetings(p["meetings"])))
    parts.append("Fits your schedule." if w.get("busy_used") and not a["skipped_check"] else
                 "Schedule not checked." if not w.get("busy_used") else "Schedule check skipped for a section with no set time.")
    for b in blocked:
        parts.append("Section %s opened too but %s, so I skipped it." % (b["sec"]["section"], b["reason"]))
    for x in others[:2]:
        parts.append("Also usable: section %s (class %s) %s." % (x["sec"]["section"], x["sec"]["class_nbr"],
                                                                 fmt_meetings(x["sec"]["meetings"])))
    if a["caveats"]:
        parts.append("Caveat: " + "; ".join(a["caveats"]) + ".")
    if link:
        parts.append("Link: " + link)
    parts.append("Call if no reply in %d min: %s." % (FOLLOW_UP_MINUTES, call) if call == "yes" else "Text only (call=no).")
    return ev, " ".join(parts)


def backup_event(w, a, backups):
    sec = a["sec"]
    ev = {"type": "BACKUP_AVAILABLE", "watch": w["id"], "class_nbr": sec["class_nbr"], "course": course_name(sec),
          "section": sec["section"], "reason": a["reason"],
          "backups": [{"class_nbr": b["sec"]["class_nbr"], "section": b["sec"]["section"],
                       "when": fmt_meetings(b["sec"]["meetings"]),
                       "link": registration_link(w["source"], w["term"], b["sec"])} for b in backups]}
    first = backups[0]["sec"]
    line = ("Section %s of %s opened, but %s. Section %s (class %s) %s is open and works instead." % (
        sec["section"], course_name(sec), a["reason"], first["section"], first["class_nbr"], fmt_meetings(first["meetings"])))
    if ev["backups"][0]["link"]:
        line += " Link: " + ev["backups"][0]["link"]
    return ev, line


# ---------- one check of one watch ----------

def check_watch(w, secs, busy, prefs, now):
    events, lines = [], []
    cands = candidates(w, secs)
    assessed = {s["class_nbr"]: assess(s, secs, busy) for s in cands}
    prev_ok, alerted = w.get("ok", {}), set(w.get("alerted", []))
    if w.get("baselined"):
        fresh = [a for n, a in assessed.items() if a["usable"] and not prev_ok.get(n)]
        if fresh:
            fresh.sort(key=lambda a: -seats(a["sec"]))
            best = fresh[0]
            others = [a for a in assessed.values() if a["usable"] and a is not best]
            blocked = [a for a in assessed.values() if a["open"] and not a["usable"]]
            ev, line = seat_event(w, best, others, blocked, [], prefs, now)
            events.append(ev), lines.append(line)
            w["alerted"], w["acked"], w["alerted_at"] = sorted(alerted | {a["sec"]["class_nbr"] for a in fresh}), False, stamp(now)
            alerted = set(w["alerted"])
        if w.get("class_nbr"):  # a single-section watch that opened but can't be taken: offer another section
            a = next(iter(assessed.values()), None)
            nbr = w["class_nbr"]
            if a and a["open"] and not a["usable"] and nbr not in w.get("blocked_told", []):
                bk = backups_for(w, secs, busy, {nbr})
                if bk:
                    ev, line = backup_event(w, a, bk)
                    events.append(ev), lines.append(line)
                    w["blocked_told"] = sorted(set(w.get("blocked_told", [])) | {nbr})
            if a and not a["open"]:
                w["blocked_told"] = [n for n in w.get("blocked_told", []) if n != nbr]
        for n in sorted(alerted):
            if not (assessed.get(n) and assessed[n]["usable"]):
                sec = next((s for s in secs if s["class_nbr"] == n), None)
                label = ("%s sec %s" % (course_name(sec), sec["section"])) if sec else "the section"
                events.append({"type": "CLOSED_AGAIN", "watch": w["id"], "class_nbr": n})
                lines.append("It filled again: %s (class %s). Still watching." % (label, n))
                w["alerted"] = [x for x in w["alerted"] if x != n]
    w["ok"] = {n: a["usable"] for n, a in assessed.items()}
    w["baselined"] = True
    return events, lines


def check_all(a, st, busy):
    now = parse_now(getattr(a, "now", None))
    events, lines, changed, cache, keep = [], [], False, {}, []
    ok_fetch = bad_fetch = 0
    last_err = None
    today = now.date().isoformat()
    for w in st["watches"]:
        if w.get("expires") and w["expires"] < today:
            events.append({"type": "WATCH_EXPIRED", "watch": w["id"]})
            lines.append("Watch %s (%s) ended: it reached its end date (%s)." % (w["id"], w["label"], w["expires"]))
            changed = True
            continue
        if w.get("snooze_until") and parse_now(w["snooze_until"]) > now:
            keep.append(w)
            continue
        key = (json.dumps(w["source"], sort_keys=True), w["term"], w["subject"], w["number"])
        try:
            if key not in cache:
                cache[key] = fetch_course(w["source"], w["term"], w["subject"], w["number"], getattr(a, "rows", None))
            secs = cache[key]
            ok_fetch += 1
        except Fail as e:
            if e.code not in (3, 4):
                raise
            bad_fetch, last_err = bad_fetch + 1, e
            w["errors"] = w.get("errors", 0) + 1
            changed = True
            if w["errors"] == MAX_ERRORS:
                events.append({"type": "WATCH_BLIND", "watch": w["id"], "errors": w["errors"]})
                lines.append("I can't reach the class data for %s right now, so this watch is blind. I'll keep trying." % w["label"])
            keep.append(w)
            continue
        if w.get("errors"):
            w["errors"], changed = 0, True
        if w.get("class_nbr") and not any(s["class_nbr"] == w["class_nbr"] for s in secs):
            events.append({"type": "SECTION_MISSING", "watch": w["id"], "class_nbr": w["class_nbr"]})
            lines.append("Class %s is no longer in the school's class data (it may have been cancelled). Watch removed." % w["class_nbr"])
            changed = True
            continue
        before = json.dumps([w.get(k) for k in ("ok", "alerted", "blocked_told", "baselined")], sort_keys=True)
        ev, ln = check_watch(w, secs, busy, st["prefs"], now)
        events += ev
        lines += ln
        changed = changed or ev or before != json.dumps([w.get(k) for k in ("ok", "alerted", "blocked_told", "baselined")], sort_keys=True)
        keep.append(w)
    st["watches"] = keep
    fatal = last_err if (bad_fetch and not ok_fetch and not events) else None
    return events, lines, changed, fatal


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
        who = (" " + s["instructors"][0]) if s["instructors"] else ""
        print("%s | %s %s sec %s%s | %s | %s%s" % (
            s["class_nbr"], course_name(s), s["comp"], s["section"], who, fmt_meetings(s["meetings"]), status_line(s),
            " | " + ", ".join(flags) if flags else ""))
    if len(rows) > a.limit:
        print("... %d more not shown; narrow with --number, --comp, --instructor or --status open|closed" % (len(rows) - a.limit))
    return 0


def load_busy(path):
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise Fail(2, "Cannot read --busy file (%s)" % e)


def cmd_watch_add(a, st):
    if len([w for w in st["watches"]]) >= MAX_WATCHES:
        raise Fail(2, "Already watching %d things; remove one first" % MAX_WATCHES)
    if not (a.subject and a.number and a.term):
        raise Fail(2, "--term, --subject and --number are required")
    source, now, busy = source_from_args(a), parse_now(a.now), load_busy(a.busy)
    filters = {k: v for k, v in (("instructor", a.instructor), ("campus", a.campus), ("online", a.online or None),
                                 ("comp", a.comp)) if v}
    w = {"id": "w%d" % st["next_id"], "term": a.term, "subject": a.subject.upper(), "number": str(a.number),
         "source": source, "class_nbr": a.cls or "", "filters": filters, "label": a.label or "",
         "busy_used": bool(busy), "created": stamp(now), "ok": {}, "alerted": [], "blocked_told": [],
         "baselined": False, "errors": 0, "snooze_until": None, "acked": False}
    for x in st["watches"]:
        if all(x.get(k) == w[k] for k in ("term", "subject", "number", "class_nbr", "filters", "source")):
            print("Already watching %s: %s" % (x["id"], x["label"]))
            return 0
    if source["source"] == "rows" and not a.rows:
        w["label"] = w["label"] or "%s %s" % (w["subject"], w["number"])
        print("Watching %s. The first check sets the baseline." % w["label"])
    else:
        secs = fetch_course(source, a.term, a.subject, a.number, a.rows)
        cands = candidates(w, secs)
        if not cands:
            if a.cls:
                raise Fail(6, "Class number %s was not found in %s %s" % (a.cls, a.subject.upper(), a.number))
            same = sorted({n for s in secs for n in s["instructors"]})
            raise Fail(6, "No %s %s sections match%s" % (a.subject.upper(), a.number,
                                                          (" (instructors this term: " + ", ".join(same[:8]) + ")") if same else ""))
        assessed = [assess(s, secs, busy) for s in cands]
        w["label"] = w["label"] or ("%s sec %s" % (course_name(cands[0]), cands[0]["section"]) if a.cls else
                                    course_name(cands[0]) + (" (%s)" % a.instructor if a.instructor else ""))
        print("Watching %s: %d section%s match." % (w["label"], len(cands), "" if len(cands) == 1 else "s"))
        for s in cands[:8]:
            print("FOUND " + describe(s))
        if len(cands) > 8:
            print("FOUND and %d more sections" % (len(cands) - 8))
        usable = [x for x in assessed if x["usable"]]
        for x in sorted(usable, key=lambda x: -seats(x["sec"]))[:3]:
            link = registration_link(source, a.term, x["sec"])
            print("ALREADY_OPEN class %s section %s, %d seat%s, usable now%s" % (
                x["sec"]["class_nbr"], x["sec"]["section"], seats(x["sec"]), "" if seats(x["sec"]) == 1 else "s",
                (" | " + link) if link else ""))
        for x in assessed:
            if x["open"] and not x["usable"]:
                print("BLOCKED class %s section %s has a seat but %s" % (x["sec"]["class_nbr"], x["sec"]["section"], x["reason"]))
        if a.cls and not usable:
            bk = backups_for(w, secs, busy, {a.cls})
            for b in bk:
                print("BACKUP class %s section %s %s is open and works" % (
                    b["sec"]["class_nbr"], b["sec"]["section"], fmt_meetings(b["sec"]["meetings"])))
        if not usable:
            print("NOTHING_USABLE_YET")
        w["ok"] = {x["sec"]["class_nbr"]: x["usable"] for x in assessed}
        w["baselined"] = True
        deadlines = [s["deadline"] for s in cands if s["deadline"]]
        end = now.date() + timedelta(days=EXPIRE_DAYS)
        if deadlines:
            end = min(end, datetime.strptime(min(deadlines), "%Y-%m-%d").date())
    w["expires"] = (end if (source["source"] != "rows" or a.rows) else now.date() + timedelta(days=EXPIRE_DAYS)).isoformat()
    st["next_id"] += 1
    st["watches"].append(w)
    save_state(st)
    print("SAVED %s expires=%s" % (w["id"], w["expires"]))
    return 0


def cmd_watch(a):
    st = load_state()
    if a.action == "list":
        p = st["prefs"]
        print("PREFS calls=%s quiet=%s-%s" % ({True: "yes", False: "no", None: "not_asked"}[p.get("calls_ok")],
                                             p["quiet_start"], p["quiet_end"]))
        if not st["watches"]:
            print("Nothing is being watched.")
        for w in st["watches"]:
            what = ("class " + w["class_nbr"]) if w["class_nbr"] else "any matching section"
            extra = (", snoozed until " + w["snooze_until"]) if w.get("snooze_until") else ""
            print("%s | %s | %s | %s%s | expires %s" % (w["id"], w["label"], what,
                                                       w["source"].get("host") or w["source"]["source"], extra, w.get("expires")))
        return 0
    if a.action == "remove":
        n = len(st["watches"])
        st["watches"] = [w for w in st["watches"] if not ((a.id and w["id"] == a.id) or (a.cls and w["class_nbr"] == a.cls))]
        save_state(st)
        print("Removed." if len(st["watches"]) < n else "No such watch.")
        return 0
    return cmd_watch_add(a, st)


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
    busy = load_busy(a.busy)
    st = load_state()
    if not st["watches"]:
        raise Fail(5, "Nothing is being watched")
    events, lines, changed, fatal = check_all(a, st, busy)
    if changed:
        save_state(st)  # failure counts must persist even when the whole check failed
    if fatal:
        raise fatal
    return emit(events, lines)


def cmd_why(a):
    """Explain why watched sections that show a seat did not produce an alert."""
    busy = load_busy(a.busy)
    st = load_state()
    if not st["watches"]:
        raise Fail(5, "Nothing is being watched")
    said = False
    for w in st["watches"]:
        secs = fetch_course(w["source"], w["term"], w["subject"], w["number"], getattr(a, "rows", None))
        for s in candidates(w, secs):
            x = assess(s, secs, busy)
            if x["open"] and not x["usable"]:
                said = True
                print("Section %s of %s has a seat but %s." % (s["section"], course_name(s), x["reason"]))
    if not said:
        print("Nothing watched has an open seat that I held back.")
    return 0


def with_watch(a, change, word):
    st = load_state()
    w = next((w for w in st["watches"] if w["id"] == a.id), None)
    if not w:
        raise Fail(6, "No watch with id %s" % a.id)
    change(w)
    save_state(st)
    print("%s %s %s" % (word, w["id"], w["label"]))
    return 0


def cmd_prefs(a):
    st = load_state()
    p = st["prefs"]
    if a.calls:
        p["calls_ok"] = a.calls == "yes"
    if a.quiet:
        try:
            s, e = (datetime.strptime(x.strip(), "%H:%M").strftime("%H:%M") for x in a.quiet.split("-"))
        except ValueError:
            raise Fail(2, "--quiet looks like 22:00-07:30")
        p["quiet_start"], p["quiet_end"] = s, e
    save_state(st)
    print("PREFS calls=%s quiet=%s-%s" % ({True: "yes", False: "no", None: "not_asked"}[p.get("calls_ok")],
                                         p["quiet_start"], p["quiet_end"]))
    return 0


def add_source_args(s, required):
    s.add_argument("--source", choices=["asu", "banner", "rows"], required=required,
                   help="where seat data comes from")
    s.add_argument("--host", help="banner: the school's registration host, e.g. reg.school.edu")
    s.add_argument("--school", help="rows: a label for the school")
    s.add_argument("--rows", help="rows: JSON file of sections read from the school's class search page")


def build_parser():
    p = argparse.ArgumentParser(prog="its_done_bro.py", description="Watch classes and get alerted when a seat you can take opens.")
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
    s.add_argument("--class", dest="cls", help="watch just this section (class number); leave out to watch the whole course")
    s.add_argument("--term")
    s.add_argument("--subject")
    s.add_argument("--number")
    s.add_argument("--instructor", help="course watch: instructor name contains")
    s.add_argument("--campus", help="course watch: campus name contains")
    s.add_argument("--online", action="store_true", help="course watch: online sections only")
    s.add_argument("--comp", help="course watch: component type (default: lectures)")
    s.add_argument("--label")
    s.add_argument("--busy", help="JSON file of the student's busy blocks")
    s.add_argument("--now", help="student's local time, e.g. 2026-10-24T16:30")
    s.add_argument("--id", help="remove: the watch id, e.g. w1")
    s.set_defaults(fn=cmd_watch)
    for name, fn in (("check", cmd_check), ("why", cmd_why)):
        s = sub.add_parser(name, help="compare current seats with the last check" if name == "check"
                           else "explain why an open seat did not produce an alert")
        s.add_argument("--busy", help="JSON file of the student's busy blocks")
        s.add_argument("--rows", help="JSON rows read from a school's class search page (rows source)")
        if name == "check":
            s.add_argument("--now", help="student's local time, e.g. 2026-10-24T16:30")
        s.set_defaults(fn=fn)
    for name, fn, help_ in (("ack", lambda a: with_watch(a, lambda w: w.update(acked=True), "ACKED"), "student saw the alert; no call needed"),
                            ("snooze", lambda a: with_watch(
                                a, lambda w: w.update(snooze_until=stamp(parse_now(a.now) + timedelta(minutes=a.minutes))), "SNOOZED"),
                             "pause a watch")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("id")
        if name == "snooze":
            s.add_argument("--minutes", type=int, required=True)
            s.add_argument("--now", help="student's local time")
        s.set_defaults(fn=fn)
    s = sub.add_parser("prefs", help="save the call preference and quiet hours")
    s.add_argument("--calls", choices=["yes", "no"])
    s.add_argument("--quiet", help="HH:MM-HH:MM, e.g. 22:00-07:30")
    s.set_defaults(fn=cmd_prefs)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "watch" and a.action == "add" and not a.source:
        print("ERROR: --source is required")
        return 2
    if a.cmd == "watch" and a.action == "remove" and not (a.id or a.cls):
        print("ERROR: --id or --class is required")
        return 2
    try:
        return a.fn(a)
    except Fail as e:
        print("ERROR: " + e.msg)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
