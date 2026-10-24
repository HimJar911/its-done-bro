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

Cubbie keeps watching in the background.

## How it works

1. You tell Cubbie once which class is full.
2. Cubbie keeps checking the school's public class search.
3. A small script compares the current seats with the last check and reports only what changed.
4. If something opened, Cubbie checks it against your calendar and texts you what to do.

## Why this belongs in Cubbie

Seat alerts already exist as websites and apps. They only know the class, so the most they can say is "a seat opened."

Cubbie knows you too, so it can finish the thought:

- It knows your schedule, so it tells you whether the seat clashes with your job or another class.
- It remembers which of your classes you could give up, so it can suggest the swap.
- It lives in your texts, so the alert reaches you where you'll actually see it. There's no new app or account.
- It can take you straight to the registration page, so the seat is a tap away.

## What it handles

- Lecture plus lab: a lecture only counts as open if a linked lab or recitation can also be taken.
- Clashes: it checks the opening against your schedule and names what overlaps.
- Swaps, not drops: it never suggests dropping a class first, so you can't end up with neither.
- Reserved seats and instructor consent: it warns you the seat may not be open to you.

## What it never does

It never enrolls, drops, pays or signs in for you. You finish in your school's own system.

## Install

Text Cubbie this link, then reply "yes".

```
https://github.com/HimJar911/seat-sniper
```
