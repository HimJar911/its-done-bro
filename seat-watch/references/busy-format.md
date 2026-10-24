# busy.json

Cubbie builds this from the student's calendar and remembered classes and passes it to `check --busy busy.json`.
The script cannot read the calendar itself.

```json
[
  {"title": "ENG 101", "days": "M W F", "start": "8:00 AM", "end": "8:50 AM"},
  {"title": "Part-time job", "days": "Th", "start": "9:00 AM", "end": "12:00 PM"}
]
```

- `days`: ASU's tokens, space separated: `M T W Th F Sa Su` (`MWF` also works).
- `start` / `end`: `8:00 AM` or `08:00`. Local time of the school (Arizona has no daylight saving time).
- Only recurring weekly blocks matter here. Leave out one-off events.
- A section with no set meeting time (online, async) skips the conflict check.
