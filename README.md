# Seat Sniper

A Cubbie Skill that watches the classes you couldn't get into and texts you the moment a seat opens.

## The problem

Registration week means refreshing a class page between everything else you have going on. A seat opens at 2:07 and is
gone by 2:09. You can't watch a page all day. Cubbie can.

## What it looks like

```text
You:    Intro Bio is full. Tell me if anything opens.
Cubbie: Watching BIO 101 sec 02 (T Th 1:30-2:45 PM). It's full right now, and the waitlist has room.
        I'll only text you when something changes.

        ...meanwhile you use Cubbie for everything else...

You:    Can you move my study group to Thursday?
Cubbie: Done. Moved to Thursday 6 PM.

        ...two days later...

Cubbie: Seat opened: BIO 101 sec 02, class 30002, T Th 1:30-2:45 PM. 1 seat left.
        It needs a lab too: class 30011, Fri 9:00-11:45 AM, 3 seats.
        Clash: your Chem lecture (T Th 2:00). Swap it for this?
You:    yes
Cubbie: Class numbers:
        30002
        30011
        Registration page is below. Sign in and finish the swap yourself.
```

Cubbie keeps watching in the background while you talk to it about anything else. When nothing has changed, it doesn't
text you about it.

## How it works

1. You tell Cubbie once which class is full.
2. Cubbie keeps checking the school's public class search.
3. A small script compares the current seats with the last check and reports only what changed.
4. If something opened, Cubbie checks it against your calendar and texts you what to do.

## Why this belongs in Cubbie

A seat-tracker website can tell you a seat opened. It can't tell you the seat clashes with your job, that the lecture
is open but every lab is full, or which of your classes to swap out. Seat Sniper uses what Cubbie already has: your
calendar, your memory of which classes could move, texting, a schedule it runs on its own, and a browser to hand you
the registration page.

## What it handles

- Lecture plus lab: a lecture only counts as open if a linked lab or recitation can also be taken.
- Waitlists: it tells you when a waitlist spot opens or the line moves, and says clearly it is not a seat.
- Clashes: it checks the opening against your schedule and names what overlaps.
- Swaps, not drops: it never suggests dropping a class first, so you can't end up with neither.
- Reserved seats and instructor consent: it warns you the seat may not be open to you.
- Silence: no message when nothing changed.

## What it never does

It never enrolls, drops, pays or signs in for you. You finish in your school's own system. The only thing it sends
anywhere is a request to the school's public class search.

## Install

Text Cubbie this link, then reply "yes".

```
https://github.com/HimJar911/seat-sniper
```
