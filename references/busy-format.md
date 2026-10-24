# busy.json

Cubbie builds this from the student's calendar and remembered classes and passes it to `check --busy busy.json`.
The script cannot read the calendar itself.

```json
[
  {"title": "Chem lecture", "days": "M W F", "start": "8:00 AM", "end": "8:50 AM"},
  {"title": "Part-time job", "days": "Th", "start": "9:00 AM", "end": "12:00 PM"}
]
```

- `days`: weekday tokens, space separated: `M T W Th F Sa Su` (`MWF` also works).
- `start` / `end`: `8:00 AM`, `08:00` or `0800`. Local time of the school.
- Only recurring weekly blocks matter here. Leave out one-off events.
- A section with no set meeting time (online, async) skips the conflict check.
