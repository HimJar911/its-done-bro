---
name: seat-sniper
description: Watches full class sections at the student's school and texts them the moment a seat or waitlist spot opens, checked against their schedule. Use when a student says a class or section is full, or asks to be told when a seat opens. Not for general registration questions.
---

# Seat Sniper

Registration is the stretch of the year when a student refreshes a class page every few minutes. This Skill does the
refreshing: it watches the sections the student needs, and when a seat or a waitlist spot opens it says exactly what to
do about it, including any time conflict with their schedule and any linked lab or recitation they also need.

It never enrolls, drops, pays or signs in for the student. It tells them, and they act.

## When to use

- "Intro Bio is full, tell me if a spot opens."
- "I need any section of Calc II that doesn't clash with my job."
- "Watch this class for me" (with a class number).
- "Check my watched classes now."

Do not use it for how registration works, what to take, degree planning or waitlist policy. Answer those normally.

## Setup

None. The script uses only the Python standard library. Run it from this Skill's folder.

## Which school and which data source

Seat counts come from the school's own public class search, which needs no sign-in. Work out the student's school
first (remembered, or ask once), then pick the source. Details and how to add a school are in `references/adapters.md`.

| The school's class search is... | Use |
| --- | --- |
| Ellucian Banner 9 ("Browse Classes" / "Class Search", address contains `StudentRegistrationSsb`) | `--source banner --host <registration host>` |
| Arizona State University | `--source asu` |
| Anything else | `--source rows`: read the page yourself and pass a small JSON file (`references/adapters.md`) |

To find a Banner host, search the web for the school's class search page and take the host from its address. Check it
with `terms`; if it lists terms, it works. If a school asks for a sign-in just to search classes, use `rows`, and if
that is also blocked, say so and stop.

Term codes differ by school. For Banner, run `terms` and pick the one matching the term the student means.

## Steps: start a watch

1. Find out what the student needs. Ask one question at a time and suggest a default:
   - Which course and term? (default: the upcoming term)
   - Any section, or one specific section?
   - Which of their current classes could move? (Remember the answer with Cubbie's memory so they are not asked again.)
2. List the sections. Keep it short; filter with `--status closed` and, if useful, `--comp`:

   ```bash
   python3 scripts/seat_sniper.py lookup --source banner --host <host> --term <term> --subject <SUBJ> --number <NUM> --status closed
   ```

   Send at most five lines, plain text. Let the student pick.
3. Save the watch (at most 5 at a time):

   ```bash
   python3 scripts/seat_sniper.py watch add --source banner --host <host> --term <term> --subject <SUBJ> --number <NUM> --class <class number>
   ```

   The output says the section's current state. If it is already enrollable, tell the student right away and go to
   "When something opens". If it says the waitlist has room, tell them they can join it now and ask whether they want
   to be told about seats only, or also about waitlist movement (default: both).
4. Agree on how often to check, then create a recurring check-in. Suggest every hour, and every 5 minutes around the
   hour the student's registration opens if Cubbie allows that often. Create the check-in only after the student says yes.
   Word it so it makes sense days later: "Run the seat-sniper Skill's check command and message the student only if it
   reports a change."
5. Confirm in one short line what is watched and how often.

## Steps: every check

Read the student's calendar and remembered classes first, and write their weekly commitments to a small JSON file
(`references/busy-format.md`). Then run:

```bash
python3 scripts/seat_sniper.py check --busy busy.json
```

For a `rows` school, rebuild the rows file from the class search page first and add `--rows <file>`.

- Output `NO CHANGE`: **send the student no message at all.** Do not say "nothing changed". A Skill that texts every
  hour gets uninstalled.
- Exit code 10, with lines starting `EVENT` and `SUMMARY`: go to "When something opens".
- Anything else: see "When something fails".

The student can also say "check now". Run the same command and answer, even when nothing changed (then say so in one line).

## When something opens

The `SUMMARY` line has the facts. Send one message, not two. Lead with the answer, plain text, short lines.

- `SEAT_OPENED`: a real seat. Include the course, class number, days and time, and seats left; the linked lab or
  recitation they also need (class number and time); any named conflict; the caveat line if present (reserved seats or
  instructor consent: the seat may not be open to them).
- `WAITLIST_OPENED`: not a seat. A waitlist spot opened. Say that plainly, give how many spots are taken, and offer the
  student the chance to join. Joining is their action, in their school's system.
- `WAITLIST_MOVED`: the waitlist got shorter, still no seat. One line. Skip it if the student chose seats only.
- `SECTION_MISSING` or `WATCH_EXPIRED`: the watch is already removed. Tell the student in one line why.

If there is a conflict, offer a **swap**, never a drop. If the school has a swap or replace-a-class feature, point the
student to it. If it does not, tell them to add the new class first and drop the old one only after the add succeeds,
so they cannot end up with neither.

When they say yes, send the class numbers on their own lines so they can copy them, and the link to the school's
registration or enrollment page (look it up for their school; do not guess). Tell them to sign in and finish it
themselves. If they ask, open the page in Cubbie's browser, stop at the sign-in, and hand the browser to them for the
password and any two-factor prompt. Never ask for a password in the chat.

Then ask whether they got in. When they say yes, stop that watch:

```bash
python3 scripts/seat_sniper.py watch remove --class <class number>
```

## Replies

Short messages, plain text, no Markdown, one idea each. Put links on their own line. Never state a seat count or a time
the script did not print. If something is uncertain, say so in one line.

Example:

```text
Seat opened: BIO 101 sec 02, class 30002, T Th 1:30-2:45 PM. 1 seat left.
It needs a lab too: class 30011, Fri 9:00-11:45 AM, 3 seats.
Clash: your Chem lecture (T Th 2:00). Swap it for this?
```

## When something fails

| Result | Meaning | What to text |
| --- | --- | --- |
| Exit 0, `NO CHANGE` | Nothing new | Nothing (unless the student asked "check now") |
| Exit 3 | School's class data unreachable | One line: the class data isn't responding, I'll try again next check. Do not guess seats |
| Exit 4 | Data is in an unexpected shape, or needs a login | Say seat data is unavailable right now and stop checking until it is fixed. Do not guess |
| Exit 5 | Nothing is watched | Offer to start a watch |
| Exit 6 | Class number not found | Ask them to re-pick from the list |
| Exit 2 | Bad command | Fix the command and run it again once |
| Calendar not connected | No schedule to check against | Ask for the days and times of their other classes instead, or alert without a conflict check and say so |

## Safety

- Only the student's yes starts a watch or a check-in. Say what is watched and how often.
- Never enroll, drop, pay or log in for the student.
- Data goes only to the school's public class search. Nothing about the student is sent anywhere.
- Poll gently: do not run checks more often than the student agreed to.
- Never promise they will get the seat. Seats go fast and some are reserved.
- A simulated replay (`check --sample`) is for demos and must be labeled simulated everywhere it is shown.
