import json, os, sys, tempfile, unittest, io, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import seat_watch as sw


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = sw.main(argv)
    return code, buf.getvalue()


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["SEAT_WATCH_STATE"] = os.path.join(self.tmp, "state.json")
        self.before, self.after = sw.load_snapshot("snapshot_before.json"), sw.load_snapshot("snapshot_after.json")
        self.current = self.before
        sw.fetch_asu_course = lambda t, s, n: self.current

    def test_parsing(self):
        self.assertEqual(sw.parse_days(["M W"]), [0, 2])
        self.assertEqual(sw.parse_days(["T Th"]), [1, 3])
        self.assertEqual(sw.parse_days(["M W F"]), [0, 2, 4])
        self.assertEqual(sw.parse_days(["MWF"]), [0, 2, 4])
        self.assertEqual(sw.parse_days([""]), [])
        self.assertEqual(sw.parse_days(["&nbsp;"]), [])
        self.assertEqual(sw.parse_time("9:00 AM"), 540)
        self.assertEqual(sw.parse_time("12:00 PM"), 720)
        self.assertEqual(sw.parse_time("12:30 AM"), 30)
        self.assertEqual(sw.parse_time("13:15"), 795)
        self.assertIsNone(sw.parse_time("None"))
        self.assertIsNone(sw.parse_time(None))

    def test_transition_alerts_once(self):
        self.assertEqual(run(["watch", "add", "--term", "2271", "--subject", "CHM", "--number", "116", "--class", "16222"])[0], 0)
        self.assertEqual(run(["check"])[0], 0)           # still closed: silent
        self.current = self.after
        code, out = run(["check"])
        self.assertEqual(code, 10)
        self.assertIn("SEAT_OPENED", out)
        self.assertIn("linked LAB", out)
        self.assertEqual(run(["check"])[0], 0)           # no repeat alert
        self.current = self.before                        # closes again
        self.assertEqual(run(["check"])[0], 0)
        self.current = self.after                         # opens again -> alert again
        self.assertEqual(run(["check"])[0], 10)

    def test_lecture_open_but_every_lab_full_is_silent(self):
        run(["watch", "add", "--term", "2271", "--subject", "CHM", "--number", "116", "--class", "16222"])
        import copy
        cur = copy.deepcopy(self.after)
        for s in cur:
            if s["comp"] == "LAB":
                s["enrl"] = s["cap"]; s["status"] = "C"
        self.current = cur
        self.assertEqual(run(["check"])[0], 0)           # half-open: no alert
        for s in cur:
            if s["class_nbr"] == "16224":
                s["enrl"] = s["cap"] - 1; s["status"] = "O"
        self.assertEqual(run(["check"])[0], 10)          # pair now complete: alert

    def test_conflict_and_online_skip(self):
        busy = [{"title": "Calc", "days": "M W F", "start": "8:30 AM", "end": "9:30 AM"}]
        lec = next(s for s in self.after if s["class_nbr"] == "16222")
        self.assertEqual(sw.overlaps(lec, busy), ["Calc"])
        self.assertEqual(sw.overlaps(lec, [{"title": "x", "days": "T Th", "start": "8:00 AM", "end": "9:00 AM"}]), [])
        self.assertEqual(sw.overlaps(lec, [{"title": "x", "days": "M", "start": "8:50 AM", "end": "9:30 AM"}]), [])  # touching, not overlapping
        online = dict(lec, days=[], start=None, end=None)
        self.assertIsNone(sw.overlaps(online, busy))

    def test_other_school_rows(self):
        rows = os.path.join(self.tmp, "rows.json")
        json.dump([{"class_nbr": "77", "subject": "BIO", "number": "101", "section": "A", "comp": "LEC",
                    "enrl": 50, "cap": 50, "days": "T Th", "start": "10:00 AM", "end": "11:15 AM"}], open(rows, "w"))
        self.assertEqual(run(["watch", "add", "--school", "otheru", "--class", "77", "--subject", "BIO", "--number", "101"])[0], 0)
        self.assertEqual(run(["check", "--rows", rows])[0], 0)   # sets baseline (closed)
        json.dump([{"class_nbr": "77", "subject": "BIO", "number": "101", "section": "A", "comp": "LEC",
                    "enrl": 49, "cap": 50, "days": "T Th", "start": "10:00 AM", "end": "11:15 AM"}], open(rows, "w"))
        code, out = run(["check", "--rows", rows])
        self.assertEqual(code, 10); self.assertIn("SEAT_OPENED", out)

    def test_error_codes(self):
        self.assertEqual(run(["check"])[0], 5)
        self.assertEqual(run(["watch", "add", "--term", "2271", "--subject", "CHM", "--number", "116", "--class", "0"])[0], 6)

    def test_sample_replay_is_stateless(self):
        code, out = run(["check", "--sample"])
        self.assertEqual(code, 10); self.assertIn("SIMULATED", out)
        self.assertFalse(os.path.exists(os.environ["SEAT_WATCH_STATE"]))


if __name__ == "__main__":
    unittest.main()
