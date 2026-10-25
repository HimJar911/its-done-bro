# Schools and data formats

It's Done Bro reads each school's public class search, with no sign-in. Pick the source that matches the school.

## `--source asu`

Term codes follow `2<yy><d>`: `d` is 1 for spring, 4 for summer, 7 for fall (Spring 2027 is `2271`). Registration links
are built for you.

## `--source banner --host <host>`

For schools whose "Browse Classes" or "Class Search" page lives under `StudentRegistrationSsb`. Take the host from the
page's address (for example `reg.example.edu`), then:

```bash
python3 scripts/its_done_bro.py terms --source banner --host reg.example.edu
python3 scripts/its_done_bro.py lookup --source banner --host reg.example.edu --term 202710 --subject BIO --number 101
```

`terms` lists the term codes; pick the one the student means. If `terms` or `lookup` exits 4, the school needs a sign-in
or is not set up this way; use `rows`. There is no deep link, so find the school's registration page for the alert.

## `--source rows` (any other school)

Open the school's public class search with the browser or web ability and write the sections of the course (including
linked labs and recitations) to a JSON file using only numbers read from the page:

```json
[
  {"class_nbr": "77", "subject": "BIO", "number": "101", "section": "A", "comp": "LEC",
   "enrl": 49, "cap": 50, "days": "T Th", "start": "10:00 AM", "end": "11:15 AM", "link": "A",
   "instructors": ["Lee"], "campus": "Main", "reserved": false, "consent": false}
]
```

- `class_nbr` is the school's unique id for the section. `enrl` and `cap` are seats taken and total.
- Several meetings: `"meetings": [{"days": "M W", "start": "9:00 AM", "end": "9:50 AM"}, ...]` instead of
  `days`/`start`/`end`.
- Give a lecture and its lab or recitation the same `link`; leave it empty when nothing is linked.
- Add the watch with `--source rows --school <name> --rows <file>`. Every check, rebuild the file and pass `--rows <file>`;
  the first check only records the baseline.

Tell the student this school is read by hand, so a wrong alert is possible.

## busy.json

The student's weekly commitments, written from their calendar and remembered classes. Only recurring weekly blocks:

```json
[
  {"title": "Chem lecture", "days": "M W F", "start": "8:00 AM", "end": "8:50 AM"},
  {"title": "Part-time job", "days": "Th", "start": "9:00 AM", "end": "12:00 PM"}
]
```

Days are `M T W Th F Sa Su`; times are `8:00 AM`, `08:00` or `0800`. A section with no set meeting time (online, async)
skips the schedule check.
