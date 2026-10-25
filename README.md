# Seat Sniper

**Get the right seat before someone else does.**

Tell Cubbie which class is full, once. It watches in the background, and when a seat opens it works out whether *you* can take it: the lab, your schedule, any restrictions. Then it texts you with the registration link, and calls if you miss it. Works across multiple universities.

<img src="assets/demo.svg" alt="Example: you text Cubbie to watch a course. When a seat opens, Cubbie texts you that the seat, recitation and schedule all work, with a registration link, and calls if you miss it." width="100%"/>

<sub>Example scenario.</sub>

## A seat opening isn't a seat you can take

Most seat alerts stop at "something opened." Registration doesn't. The lecture has a seat, but the recitation is full. The section is open, but it lands on top of your job. The seat is reserved for a major you're not.

Seat Sniper checks all of that first, so the text you get is one you can act on.

<img src="assets/compare.svg" alt="A plain seat alert only says a seat opened. Seat Sniper says the recitation is open, it fits your schedule, nothing restricts it, and a backup exists." width="100%"/>

## Say it once

Text Cubbie this link and reply **yes**:

```text
https://github.com/HimJar911/seat-sniper
```

Then talk to it like a person: **"Watch CSE 340 for me."**

That's the whole setup. You don't pick a section, a check time, or a mode. It watches every matching section of the course and keeps going while you use Cubbie for everything else.

## What it checks before it texts you

1. **Is the seat real?** The section actually has room right now.
2. **Is the rest of the package open?** If the course needs a lab or recitation, that has to be open too.
3. **Does it fit your week?** It checks the meeting times against your calendar and the classes you've told Cubbie about.
4. **Any strings attached?** Reserved seats and instructor-consent sections get flagged.
5. **If not this one, which one?** When a section opens but can't work, it looks for another that can.

Only then do you hear from it. Then it moves fast:

- **A text** with the section, the lab, and the registration link on its own line.
- **A tap-ready page.** Cubbie can open the registration page and hand it to you to sign in.
- **A phone call** if you miss the text. You say yes to calls once, and quiet hours keep it from ringing overnight.
- **A follow-up** if the seat fills again, so you're never left guessing.

## Ask it like you'd ask a friend

> **You:** Watch BIO 101, but only with Prof Lee.
> **Cubbie:** On it. Watching only Prof Lee's sections.

> **You:** Why didn't you tell me about section 3?
> **Cubbie:** Section 3 had a seat, but its required lab was full.

> **You:** Pause it for an hour.
> **Cubbie:** Paused until 3:40.

> **You:** I got in, thanks!
> **Cubbie:** Nice. I've stopped watching it.

## Hands off your registration

Seat Sniper never enrolls, drops, swaps, pays or signs in for you, and it never asks for your password. When a class clashes with one you're already in, it names the conflict and offers an alternative instead of touching your schedule. You always make the final click.

It also looks after itself: it tells you if it ever loses sight of a school's class data, stops watching on its own when registration ends, and only ever texts you.

## Under the hood

Seat Sniper is a Cubbie Skill: `SKILL.md` tells Cubbie when to use it and how to talk, and `scripts/seat_sniper.py` (standard library, nothing to install) reads the school's public class search, evaluates every section and remembers what changed. Cubbie handles the texting, calling and scheduling. School-specific notes are in `references/schools.md`, and `tests/` covers the seat, lab, schedule and call logic.

---

**Like Seat Sniper? [Vote for it →](https://hackathon.cubbie.ai/#gallery)**
