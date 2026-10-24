# Watching a school other than ASU (best effort)

1. Find the school's public class search page (no login) with the web or browser ability.
2. For the sections the student watches, and the lab/recitation sections linked to them, write a JSON list:

```json
[
  {"class_nbr": "77", "subject": "BIO", "number": "101", "section": "A", "comp": "LEC",
   "enrl": 49, "cap": 50, "days": "T Th", "start": "10:00 AM", "end": "11:15 AM",
   "assoc": "A", "reserved": false, "consent": false}
]
```

- `class_nbr` is the school's unique id for the section. `enrl` and `cap` are taken and total seats.
- `assoc` ties a lecture to its lab/recitation: give them the same value, and make the lecture's `section` equal to it.
  Leave `assoc` empty for a course with no linked sections.
- Only use numbers read from the page. Never estimate.

3. Add the watch once: `watch add --school <name> --class <id> --subject BIO --number 101`.
4. Every check: rebuild the file from the page and run `check --rows <file>`. The first check only records the baseline.

Tell the student this school is untested and a wrong alert is possible.
