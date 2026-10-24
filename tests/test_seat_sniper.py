import copy, json, os, sys, tempfile, unittest, io, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import seat_sniper as ss

ASU = ["--source", "asu"]
ORIG_FETCH = ss.fetch_course
WATCH = ["watch", "add"] + ASU + ["--term", "2271", "--subject", "CHM", "--number", "116"]


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = ss.main(argv)
    return code, buf.getvalue()


def banner_row(**kw):
    """Synthetic row in the shape Ellucian Banner 9's public search returns (field names verified, values made up)."""
    r = {"term": "202710", "courseReferenceNumber": "30001", "subject": "BIO", "courseNumber": "101",
         "sequenceNumber": "01", "courseTitle": "Intro Biology", "scheduleTypeDescription": "Lecture",
         "instructionalMethodDescription": "In person", "openSection": False, "seatsAvailable": 0,
         "maximumEnrollment": 40, "enrollment": 40, "waitCapacity": 10, "waitCount": 10, "linkIdentifier": None,
         "reservedSeatSummary": None,
         "meetingsFaculty": [{"meetingTime": {"beginTime": "1330", "endTime": "1445", "monday": False,
                                              "tuesday": True, "wednesday": False, "thursday": True, "friday": False,
                                              "saturday": False, "sunday": False}}]}
    r.update(kw)
    return r


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["SEAT_SNIPER_STATE"] = os.path.join(self.tmp, "state.json")
        self.before, self.after = ss.load_snapshot("snapshot_before.json"), ss.load_snapshot("snapshot_after.json")
        self.current = self.before
        ss.fetch_course = lambda source, term, subject, number, rows_file=None: self.current

    def test_parsing(self):
        self.assertEqual(ss.parse_days(["M W"]), [0, 2])
        self.assertEqual(ss.parse_days(["T Th"]), [1, 3])
        self.assertEqual(ss.parse_days(["MWF"]), [0, 2, 4])
        self.assertEqual(ss.parse_days([""]), [])
        self.assertEqual(ss.parse_days(["&nbsp;"]), [])
        self.assertEqual(ss.parse_time("9:00 AM"), 540)
        self.assertEqual(ss.parse_time("12:30 AM"), 30)
        self.assertEqual(ss.parse_time("13:15"), 795)
        self.assertEqual(ss.parse_time("1530"), 930)
        self.assertEqual(ss.parse_time("0800"), 480)
        self.assertIsNone(ss.parse_time("None"))
        self.assertIsNone(ss.parse_time(None))

    def test_banner_normalization(self):
        sec = ss.normalize_banner(banner_row(), "reg.example.edu")
        self.assertEqual((sec["class_nbr"], sec["status"], sec["cap"], sec["wait_cap"]), ("30001", "C", 40, 10))
        self.assertEqual(sec["meetings"], [{"days": [1, 3], "start": 810, "end": 885}])
        self.assertIsNone(ss.own_kind(sec))  # full, waitlist full
        online = ss.normalize_banner(banner_row(meetingsFaculty=[{"meetingTime": {"beginTime": None, "endTime": None}}]), "h")
        self.assertEqual(online["meetings"], [])
        multi = ss.normalize_banner(banner_row(meetingsFaculty=[
            {"meetingTime": {"beginTime": "0900", "endTime": "0950", "monday": True}},
            {"meetingTime": {"beginTime": "1300", "endTime": "1350", "friday": True}}]), "h")
        self.assertEqual(len(multi["meetings"]), 2)
        with self.assertRaises(ss.Fail):
            ss.normalize_banner({"nope": 1}, "h")

    def test_waitlist_kinds(self):
        full_wait = ss.normalize_banner(banner_row(waitCount=3), "h")
        self.assertEqual(ss.own_kind(full_wait), "wait")
        open_ = ss.normalize_banner(banner_row(openSection=True, seatsAvailable=2, enrollment=38), "h")
        self.assertEqual(ss.own_kind(open_), "seat")
        no_wait = ss.normalize_banner(banner_row(waitCapacity=0, waitCount=0), "h")
        self.assertIsNone(ss.own_kind(no_wait))

    def test_asu_transition_alerts_once_with_pair(self):
        self.assertEqual(run(WATCH + ["--class", "16222"])[0], 0)
        self.assertEqual(run(["check"])[0], 0)           # still closed: silent
        self.current = self.after
        code, out = run(["check"])
        self.assertEqual(code, 10)
        self.assertIn("SEAT_OPENED", out)
        self.assertIn("linked LAB", out)
        self.assertEqual(run(["check"])[0], 0)           # no repeat alert
        self.current = self.before
        self.assertEqual(run(["check"])[0], 0)
        self.current = self.after
        self.assertEqual(run(["check"])[0], 10)

    def test_lecture_open_but_every_lab_full_is_silent(self):
        run(WATCH + ["--class", "16222"])
        cur = copy.deepcopy(self.after)
        for s in cur:
            if s["comp"] == "LAB":
                s["enrl"] = s["cap"]; s["status"] = "C"
        self.current = cur
        self.assertEqual(run(["check"])[0], 0)
        for s in cur:
            if s["class_nbr"] == "16224":
                s["enrl"] = s["cap"] - 1; s["status"] = "O"
        self.assertEqual(run(["check"])[0], 10)

    def test_banner_waitlist_events(self):
        def secs(**kw):
            return [ss.normalize_banner(banner_row(**kw), "h")]
        self.current = secs()
        add = ["watch", "add", "--source", "banner", "--host", "h", "--term", "202710", "--subject", "BIO",
               "--number", "101", "--class", "30001"]
        self.assertEqual(run(add)[0], 0)
        self.assertEqual(run(["check"])[0], 0)
        self.current = secs(waitCount=9)                                   # a spot on the waitlist
        code, out = run(["check"])
        self.assertEqual(code, 10); self.assertIn("WAITLIST_OPENED", out)
        self.assertEqual(run(["check"])[0], 0)
        self.current = secs(waitCount=7)                                   # queue moved
        code, out = run(["check"])
        self.assertEqual(code, 10); self.assertIn("WAITLIST_MOVED", out)
        self.assertIn("from 9 to 7", out)
        self.current = secs(openSection=True, seatsAvailable=1, enrollment=39, waitCount=0)  # real seat
        code, out = run(["check"])
        self.assertEqual(code, 10); self.assertIn("SEAT_OPENED", out)

    def test_banner_linked_components_by_group(self):
        lec = banner_row(courseReferenceNumber="1", openSection=True, seatsAvailable=1, enrollment=39, linkIdentifier="A")
        lab = banner_row(courseReferenceNumber="2", scheduleTypeDescription="Lab", linkIdentifier="A")
        secs = [ss.normalize_banner(r, "h") for r in (lec, lab)]
        self.assertIsNone(ss.evaluate(secs[0], secs)[0])           # lecture open, lab full, no waitlist room
        lab2 = banner_row(courseReferenceNumber="2", scheduleTypeDescription="Lab", linkIdentifier="A",
                          openSection=True, seatsAvailable=3, enrollment=37)
        secs = [ss.normalize_banner(r, "h") for r in (lec, lab2)]
        kind, partners = ss.evaluate(secs[0], secs)
        self.assertEqual((kind, [p["class_nbr"] for p in partners]), ("seat", ["2"]))

    def test_conflict_uses_every_meeting_and_skips_untimed(self):
        busy = [{"title": "Job", "days": "F", "start": "1:15 PM", "end": "2:00 PM"}]
        multi = ss.normalize_banner(banner_row(meetingsFaculty=[
            {"meetingTime": {"beginTime": "0900", "endTime": "0950", "monday": True}},
            {"meetingTime": {"beginTime": "1300", "endTime": "1350", "friday": True}}]), "h")
        self.assertEqual(ss.overlaps(multi, busy), ["Job"])
        lec = next(s for s in self.after if s["class_nbr"] == "16222")
        self.assertEqual(ss.overlaps(lec, [{"title": "x", "days": "M", "start": "8:50 AM", "end": "9:30 AM"}]), [])
        online = dict(lec, meetings=[])
        self.assertIsNone(ss.overlaps(online, busy))

    def test_other_school_rows(self):
        rows = os.path.join(self.tmp, "rows.json")
        base = {"class_nbr": "77", "subject": "BIO", "number": "101", "section": "A", "comp": "LEC", "cap": 50,
                "days": "T Th", "start": "10:00 AM", "end": "11:15 AM"}
        json.dump([dict(base, enrl=50)], open(rows, "w"))
        ss.fetch_course = ORIG_FETCH  # rows source reads the file for real
        self.assertEqual(run(["watch", "add", "--source", "rows", "--school", "otheru", "--class", "77",
                              "--subject", "BIO", "--number", "101", "--term", "x"])[0], 0)
        self.assertEqual(run(["check", "--rows", rows])[0], 0)
        json.dump([dict(base, enrl=49)], open(rows, "w"))
        code, out = run(["check", "--rows", rows])
        self.assertEqual(code, 10); self.assertIn("SEAT_OPENED", out)

    def test_error_codes(self):
        self.assertEqual(run(["check"])[0], 5)
        self.assertEqual(run(WATCH + ["--class", "0"])[0], 6)
        self.assertEqual(run(["watch", "add", "--source", "banner", "--term", "1", "--subject", "A", "--number", "1",
                              "--class", "1"])[0], 2)  # banner needs --host

    def test_sample_replay_is_stateless(self):
        code, out = run(["check", "--sample"])
        self.assertEqual(code, 10); self.assertIn("SIMULATED", out)
        self.assertFalse(os.path.exists(os.environ["SEAT_SNIPER_STATE"]))


if __name__ == "__main__":
    unittest.main()
