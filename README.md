# seat-sniper

A Cubbie Skill by **State Property** for the Cubbie Hackathon (Track 1).

Your class is full. Tell Cubbie once. When a seat opens, it checks your schedule, tells you what to swap, and sends the class numbers so you can finish it in MyASU yourself.

Install: text Cubbie this link, then reply "yes".

```
https://github.com/HimJar911/seat-sniper/tree/main/seat-watch
```

(The repository link itself also works; Cubbie finds the Skill folder inside.)

## What it does

- Watches full sections (ASU built in; other schools best effort).
- Alerts only when a seat is actually enrollable: a lecture counts only if a linked lab or recitation also has a seat.
- Checks the open seat against your calendar and says what it overlaps.
- Offers a **swap**, never a drop, so you cannot end up with neither class.
- Notes reserved seats and instructor-consent sections.
- Sends nothing when nothing changed.
- Never enrolls, drops, pays or signs in for you.

## Files

- `seat-watch/SKILL.md` : the Skill Cubbie reads
- `seat-watch/scripts/seat_watch.py` : standard-library Python, no packages
- `seat-watch/assets/` : real ASU records used for a clearly labeled simulated replay
- `seat-watch/tests/` : `python -m unittest discover -s seat-watch/tests`

The replay (`check --sample`) is simulated and is always labeled so.

Seat counts come from ASU's public class search data. This project is not affiliated with Arizona State University.
