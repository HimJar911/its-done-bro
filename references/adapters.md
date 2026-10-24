# Data sources (adapters)

Every source is turned into the same section record: class number, course, component (lecture, lab...), meetings
(days and times, possibly several), enrolled, capacity, waitlist capacity and count, a link group tying a lecture to its
lab or recitation, and caveat flags. The rest of the script does not care where it came from.

## banner (Ellucian Banner 9 public class search)

Used by many US colleges. The script talks to `https://<host>/StudentRegistrationSsb/ssb/...` the same way the public
"Browse Classes" page does, with no sign-in: it opens a session, selects the term, and reads the section search results.

```bash
python3 scripts/seat_sniper.py terms --source banner --host reg.example.edu
python3 scripts/seat_sniper.py lookup --source banner --host reg.example.edu --term 202710 --subject BIO --number 101
```

- Fields used: `courseReferenceNumber` (the class number), `openSection`, `enrollment`, `maximumEnrollment`,
  `waitCapacity`, `waitCount`, `linkIdentifier` (lecture-to-lab link group), `meetingsFaculty[].meetingTime`,
  `reservedSeatSummary`.
- Tried against three Banner 9 schools' public search: terms, section lists, seat counts, waitlist counts, and times
  (including several meetings per section and online sections with none) all parsed.
- Not seen in live data, so treated as unverified: sections linked by `linkIdentifier`. The unit tests cover linking
  with synthetic rows.
- Some schools turn on a login or run a different version. Then `terms` or `lookup` exits 4; use `rows`.

## asu (Arizona State University)

ASU's public class search reads from a JSON feed. Term codes look like `2<yy><d>` where d is 1 spring, 4 summer, 7 fall
(Spring 2027 is `2271`). The seat truth is enrolled-total versus capacity; the feed's own `seatInfo` text is ignored
because it can be off by a few. Lecture-to-lab links come from `ASSOCIATEDCLASS`.

## rows (any other school)

1. Find the school's public class search page with the web or browser ability.
2. For the sections the student watches, and the lab or recitation sections linked to them, write a JSON list:

```json
[
  {"class_nbr": "77", "subject": "BIO", "number": "101", "section": "A", "comp": "LEC",
   "enrl": 49, "cap": 50, "wait_cap": 10, "wait_count": 4,
   "days": "T Th", "start": "10:00 AM", "end": "11:15 AM", "link": "A",
   "reserved": false, "consent": false}
]
```

- `class_nbr` is the school's unique id for the section. `enrl` and `cap` are taken and total seats. Leave the wait
  fields out if the school has no waitlist.
- Several meetings: use `"meetings": [{"days": "M W", "start": "9:00 AM", "end": "9:50 AM"}, ...]` instead of
  `days`/`start`/`end`.
- `link` ties a lecture to its lab or recitation: give them the same value. Leave it empty for a course with no linked
  sections.
- Only use numbers read from the page. Never estimate.

3. Add the watch once with `watch add --source rows --school <name> --class <id> --subject BIO --number 101 --term <term>`.
4. Every check: rebuild the file from the page and run `check --rows <file>`. The first check only records the baseline.

Tell the student this school is read by hand, so a wrong alert is possible.

## Adding a new platform

Write a `normalize_<platform>` function in `scripts/seat_sniper.py` that returns `make_section(...)` records, a fetch
function, and a branch in `fetch_course`. Nothing else changes.
