# seat-sniper

A Cubbie Skill that watches full class sections and texts you the moment a seat or waitlist spot opens.

Your class is full. Tell Cubbie once. When something opens, it checks your schedule, tells you what clashes and what to
swap, and sends the class numbers so you can finish it in your school's registration system yourself.

Install: text Cubbie this link, then reply "yes".

```
https://github.com/HimJar911/seat-sniper
```

## What it does

- Works across schools: Ellucian Banner 9 public class search and ASU are built in; any other school is read from its
  class search page by Cubbie.
- Alerts when a real seat is enrollable: a lecture counts only if a linked lab or recitation can also be taken.
- Tells you about waitlist spots and waitlist movement, and labels them as not a seat.
- Checks the opening against your calendar and says what it overlaps.
- Offers a **swap**, never a drop, so you cannot end up with neither class.
- Sends nothing when nothing changed.
- Never enrolls, drops, pays or signs in for you.

## Files

- `SKILL.md`: the instructions Cubbie follows
- `scripts/seat_sniper.py`: the seat checker (Python standard library only, nothing to install)

Seat counts come from each school's public class search. This project is not affiliated with any school or with Ellucian.
