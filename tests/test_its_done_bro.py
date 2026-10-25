import contextlib, io, json, os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import its_done_bro as ss

def sec(n, comp="LEC", enrl=10, cap=10, link="L1", sec_no="01", days="M W", st="9:00 AM", en="9:50 AM", **kw):
    return ss.make_section(source="asu", term="2271", subject="CSE", number="340", class_nbr=n, section=sec_no, comp=comp,
        enrl=enrl, cap=cap, status="C" if enrl >= cap else "O", link=link,
        meetings=[ss.meeting(ss.parse_days(days), st, en)] if days else [], **kw)

def run(argv):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        code = ss.main(argv)
    return code, b.getvalue()

class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.environ["ITS_DONE_BRO_STATE"] = os.path.join(self.d, "s.json")
        self.cur = []
        ss.fetch_course = lambda source, term, subject, number, rows_file=None: self.cur
        self.add = ["watch", "add", "--source", "asu", "--term", "2271", "--subject", "CSE", "--number", "340", "--now", "2026-10-24T14:00"]
        self.chk = ["check", "--now", "2026-10-24T14:05"]

    def full(self):  # two lectures full, each with a recitation
        return [sec("1", enrl=10, link="A", sec_no="04"), sec("2", comp="REC", enrl=5, cap=10, link="A", sec_no="04B", days="F"),
                sec("3", enrl=10, link="B", sec_no="06", days="T Th", st="1:00 PM", en="2:15 PM"),
                sec("4", comp="REC", enrl=5, cap=10, link="B", sec_no="06B", days="F", st="2:00 PM", en="2:50 PM")]

    def test_course_watch_alert_with_link_and_pairing(self):
        self.cur = self.full()
        self.assertEqual(run(self.add)[0], 0)
        self.assertEqual(run(self.chk)[0], 0)
        self.cur = self.full(); self.cur[0]["enrl"] = 9; self.cur[0]["status"] = "O"
        code, out = run(self.chk)
        self.assertEqual(code, 10); self.assertIn("SEAT_OPENED", out)
        self.assertIn("go.oasis.asu.edu/addclass/?STRM=2271&ASU_CLASS_NBR=1", out)
        self.assertIn("Required REC open", out)
        self.assertEqual(run(self.chk)[0], 0)  # no repeat

    def test_lecture_open_lab_full_is_silent_then_alerts(self):
        self.cur = self.full(); run(self.add)
        self.cur = self.full(); self.cur[0]["enrl"] = 9; self.cur[0]["status"] = "O"; self.cur[1]["enrl"] = 10; self.cur[1]["status"] = "C"
        self.assertEqual(run(self.chk)[0], 0)
        self.cur[1]["enrl"] = 9; self.cur[1]["status"] = "O"
        self.assertEqual(run(self.chk)[0], 10)

    def test_a_fills_while_b_opens_still_alerts(self):
        self.cur = self.full(); self.cur[0]["enrl"] = 9; self.cur[0]["status"] = "O"; run(self.add)
        self.cur = self.full(); self.cur[2]["enrl"] = 9; self.cur[2]["status"] = "O"   # A filled, B opened
        code, out = run(self.chk)
        self.assertEqual(code, 10); self.assertIn('"class_nbr": "3"', out)

    def test_conflict_blocks_and_is_reported_with_other_usable(self):
        busy = os.path.join(self.d, "busy.json")
        json.dump([{"title": "MAT 343", "days": "T Th", "start": "1:30 PM", "end": "2:30 PM"}], open(busy, "w", encoding="utf-8"))
        self.cur = self.full(); run(self.add + ["--busy", busy])
        self.cur = self.full()
        for i in (0, 2): self.cur[i]["enrl"] = 9; self.cur[i]["status"] = "O"
        code, out = run(self.chk + ["--busy", busy])
        self.assertEqual(code, 10)
        self.assertIn("MAT 343", out); self.assertIn('"class_nbr": "1"', out)   # section 04 usable, 06 blocked
        self.assertIn("opened too but", out)

    def test_conflict_only_is_silent(self):
        busy = os.path.join(self.d, "busy.json")
        json.dump([{"title": "MAT 343", "days": "T Th", "start": "1:30 PM", "end": "2:30 PM"}], open(busy, "w", encoding="utf-8"))
        self.cur = self.full(); run(self.add + ["--busy", busy])
        self.cur = self.full(); self.cur[2]["enrl"] = 9; self.cur[2]["status"] = "O"
        self.assertEqual(run(self.chk + ["--busy", busy])[0], 0)
        self.assertIn("overlaps MAT 343", run(["why", "--busy", busy])[1])

    def test_section_watch_blocked_offers_backup(self):
        busy = os.path.join(self.d, "busy.json")
        json.dump([{"title": "MAT 343", "days": "T Th", "start": "1:30 PM", "end": "2:30 PM"}], open(busy, "w", encoding="utf-8"))
        self.cur = self.full(); run(self.add + ["--class", "3", "--busy", busy])
        self.cur = self.full()
        for i in (0, 2): self.cur[i]["enrl"] = 9; self.cur[i]["status"] = "O"
        code, out = run(self.chk + ["--busy", busy])
        self.assertEqual(code, 10); self.assertIn("BACKUP_AVAILABLE", out); self.assertIn("works instead", out)

    def test_calls_quiet_hours_ack_snooze(self):
        run(["prefs", "--calls", "yes"])
        self.cur = self.full(); run(self.add)
        self.cur = self.full(); self.cur[0]["enrl"] = 9; self.cur[0]["status"] = "O"
        code, out = run(self.chk)
        self.assertIn('"call": "yes"', out); self.assertIn("follow_up_minutes", out)
        self.cur = self.full(); run(self.chk)                              # closes again
        self.cur[0]["enrl"] = 9; self.cur[0]["status"] = "O"
        code, out = run(["check", "--now", "2026-10-24T23:30"])            # quiet hours
        self.assertIn('"call": "no"', out)
        self.assertEqual(run(["ack", "w1"])[0], 0)
        self.assertEqual(run(["snooze", "w1", "--minutes", "60", "--now", "2026-10-24T23:30"])[0], 0)
        self.cur = self.full(); self.cur[2]["enrl"] = 9; self.cur[2]["status"] = "O"
        self.assertEqual(run(["check", "--now", "2026-10-24T23:45"])[0], 0)  # snoozed

    def test_closed_again_blind_expiry_corrupt(self):
        self.cur = self.full(); run(self.add)
        self.cur = self.full(); self.cur[0]["enrl"] = 9; self.cur[0]["status"] = "O"; run(self.chk)
        self.cur = self.full(); code, out = run(self.chk)
        self.assertIn("CLOSED_AGAIN", out)
        def boom(*a, **k): raise ss.Fail(3, "down")
        ss.fetch_course = boom
        for _ in range(2): self.assertEqual(run(self.chk)[0], 3)
        code, out = run(self.chk); self.assertIn("WATCH_BLIND", out)
        ss.fetch_course = lambda *a, **k: self.cur
        self.assertEqual(run(["check", "--now", "2027-01-01T10:00"])[0], 10)   # expired
        open(os.environ["ITS_DONE_BRO_STATE"], "w").write("{broken")
        code, out = run(["watch", "list"]); self.assertIn("set aside", out)

    def test_filters_and_missing(self):
        s = self.full(); s[0]["instructors"] = ["Ada Lee"]; s[2]["instructors"] = ["Bo Kim"]; self.cur = s
        run(self.add + ["--instructor", "lee"])
        st = json.load(open(os.environ["ITS_DONE_BRO_STATE"]))
        self.assertEqual(list(st["watches"][0]["ok"]), ["1"])
        self.assertEqual(run(self.add + ["--class", "999"])[0], 6)

class Parsing(unittest.TestCase):
    def test_days_and_times(self):
        self.assertEqual(ss.parse_days(["M W"]), [0, 2])
        self.assertEqual(ss.parse_days(["MWF"]), [0, 2, 4])
        self.assertEqual(ss.parse_days(["&nbsp;"]), [])
        self.assertEqual(ss.parse_time("12:30 AM"), 30)
        self.assertEqual(ss.parse_time("1530"), 930)
        self.assertIsNone(ss.parse_time("None"))

    def test_banner_row(self):
        row = {"term": "202710", "courseReferenceNumber": "30001", "subject": "BIO", "courseNumber": "101",
               "sequenceNumber": "01", "courseTitle": "Intro", "scheduleTypeDescription": "Lecture",
               "instructionalMethodDescription": "In person", "openSection": False, "maximumEnrollment": 40,
               "enrollment": 40, "linkIdentifier": None, "reservedSeatSummary": None,
               "faculty": [{"displayName": "Lee, Ada"}],
               "meetingsFaculty": [{"meetingTime": {"beginTime": "1330", "endTime": "1445", "tuesday": True, "thursday": True}}]}
        s = ss.normalize_banner(row, "reg.example.edu")
        self.assertEqual(s["meetings"], [{"days": [1, 3], "start": 810, "end": 885}])
        self.assertEqual(s["instructors"], ["Lee, Ada"])
        self.assertFalse(ss.is_open(s))
        with self.assertRaises(ss.Fail):
            ss.normalize_banner({"nope": 1}, "h")


if __name__ == "__main__":
    unittest.main()
