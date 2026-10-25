---
name: seat-sniper
description: Watches a student's full classes and texts them the moment a seat they can actually take opens, with the registration link. Use when a student says a class or section is full or asks to be told when a seat opens. Not for general registration questions.
---

# Seat Sniper

A seat opening is only useful if the student can take it. This Skill watches the course in the background and, when
something opens, checks that the required lab or recitation is also open, that it fits the student's schedule, and
whether the seat has restrictions, before it texts them. The alert comes with the registration link, a backup section if
the first option does not work, and an optional phone call if they miss the text.

It never enrolls, drops, pays or signs in for the student. It tells them, and they act.

The student talks to Cubbie in plain language ("Watch CSE 340 for me", "only with Prof Lee", "stop watching that").
Cubbie runs the commands below; the student never sees them.

## When to use

- "CSE 340 is full, tell me if a spot opens."
- "Watch BIO 101 for me, preferably with Prof Lee."
- "I need any section of Calc II that doesn't clash with my job."
- "Check my watched classes now." / "What am I watching?" / "Stop watching CSE 340."

Do not use it for how registration works, what to take or degree planning. Answer those normally.

## Setup

None. The script uses only the Python standard library. Run it from this Skill's folder: `python3 scripts/seat_sniper.py`.

## Find the school and data source

Work out the student's school first (remembered, or ask once). Seat counts come from the school's own public class search,
which needs no sign-in. See `references/schools.md` for how to find the host and term, and for schools that need the
hand-read format.

| The school's class search is... | Use |
| --- | --- |
| Arizona State University | `--source asu` |
| A "Browse Classes" / "Class Search" page whose address contains `StudentRegistrationSsb` | `--source banner --host <host>` |
| Anything else | `--source rows` (read the page and pass a file; format in `references/schools.md`) |

If a school hides class search behind a sign-in, say so and stop. Never log in for the student.

## Start a watch

1. Understand what they want. "Watch CSE 340" means every matching section of the course, so the student does not have
   to pick a magic section. Pass `--instructor`, `--campus` or `--online` only if they said so. A class number means just
   that section (`--class`). The term defaults to the one they are registering for; ask only if it is unclear.
2. Write their weekly commitments to `busy.json` from their calendar and remembered classes (format in
   `references/schools.md`) and run:

   ```bash
   python3 scripts/seat_sniper.py watch add --source <asu|banner|rows> [--host <host>] --term <term> --subject CSE --number 340 \
     --busy busy.json --now "<student's local date and time>"
   ```

3. Read the output and tell the student in one or two lines what is being watched:
   - `ALREADY_OPEN ... usable now`: a seat they can take exists right now. Tell them immediately, send the link on its
     own line, and ask if they still want a watch.
   - `BLOCKED ...`: a section has a seat but cannot be taken (required recitation full, or a clash). Name it.
   - `BACKUP ...`: another section works instead; offer it.
   - `NOTHING_USABLE_YET`: nothing to take yet; reassure them you are watching.
   - `ERROR` with exit 6: no such section; ask them to re-pick, offering the instructors listed.
4. Calls. The first time only (check Cubbie's memory), ask one question: "Want me to call too if you don't respond to a
   seat alert?" Save the answer in memory and run `python3 scripts/seat_sniper.py prefs --calls yes` (or `no`). Default
   is text only. Calls never happen between 22:00 and 07:30 unless the student changes it (`prefs --quiet 23:00-08:00`).
   Do not ask about anything else (components, quiet hours, frequency); infer or use defaults.
5. Schedule the recurring check yourself (do not ask the student how often). Check about every 10 minutes, as often as
   Cubbie allows, and create it once for all watches. Word it so it makes sense days later: "Seat Sniper check: from the
   seat-sniper Skill folder run `python3 scripts/seat_sniper.py check --busy busy.json --now <student's local date and
   time>`. Act on the output as the Skill says. If it prints NO CHANGE, send nothing."
6. Confirm in one short line.

## Every check

Refresh `busy.json` from the calendar first, then run the `check` command above.

- `NO CHANGE`: **send the student no message at all.** A Skill that texts every hour gets uninstalled.
- Exit 10, with `EVENT` and `SUMMARY` lines: see "When something opens".
- Anything else: see "When something fails".

"Check now" from the student: run the same command and answer, even if nothing changed (one line).

## When something opens

The `SUMMARY` line has the facts. One message, plain text, short lines, the class first, the link on its own line.

- `SEAT_OPENED`: a seat they can take. Include the course and section, days and time, seats left, the required lab or
  recitation (class number and time), that it fits their schedule, any caveat (reserved seats, instructor consent), and
  the registration link. If the event lists `blocked` sections, add one line ("Section 06 opened too, but it overlaps
  MAT 343, so I skipped it"). If it lists other usable sections, mention one as a backup.
  - Open the link in Cubbie's browser and hand it to the student ("tap to take over"). If the school asks for a sign-in,
    the student signs in themselves. If there is no `link`, find the school's registration page; do not guess.
  - If the event says `call=yes`, create a one-time follow-up `follow_up_minutes` later: "if the student has not replied
    since the seat alert for <class>, call them and say: A seat just opened in <class>, check your texts and register
    now." Skip it if `call=no`.
  - When the student replies in any way that shows they saw it, run `python3 scripts/seat_sniper.py ack <watch id>` and
    cancel the follow-up.
- `BACKUP_AVAILABLE`: the section they watch opened but cannot be taken (see `reason`); another does work. Offer it.
- `CLOSED_AGAIN`: one line, "It filled again. Still watching <class>." Nothing else.
- `WATCH_BLIND`: tell them once that you cannot reach the school's class data right now and you will keep trying.
- `WATCH_EXPIRED` or `SECTION_MISSING`: the watch is already removed; tell them in one line why and offer to restart.

If there is a conflict, offer a **swap**, never a drop. If the school has a swap or replace-a-class feature, point the
student to it. If it does not, tell them to add the new class first and drop the old one only after the add succeeds.

Then ask whether they got in. When they say yes, stop the watch: `python3 scripts/seat_sniper.py watch remove --id <id>`
(and remove the recurring check if no watches are left).

## Other requests

| Student says | Run, then reply in a line |
| --- | --- |
| "what am I watching?" | `watch list` |
| "stop watching CSE 340" | `watch list` to find the id, then `watch remove --id <id>` |
| "pause it for an hour" | `snooze <id> --minutes 60 --now <local time>` |
| "no calls" / "calls are fine" | `prefs --calls no` (or `yes`) and update memory |
| "why didn't you tell me about section 3?" | `why --busy busy.json`, then relay the reason |
| "only Prof Lee" on an existing course watch | `watch remove --id <id>`, then add again with `--instructor Lee` |

A student can have up to 10 watches. Watches end on their own after 30 days or at the enrollment deadline.

## Replies

Short messages, plain text, no Markdown, one idea each. Lead with the class. Never state a seat count or a time the script
did not print.

```text
Seat found: BIO 101 sec 04, T Th 1:30-2:45 PM. 1 seat open.
Its recitation (class 30011, Fri 9:00) is open too, and it fits your schedule.
Section 06 opened too but overlaps your Chem lecture, so I skipped it.
Tap to register:
https://example.edu/register
```

## When something fails

| Result | What to do |
| --- | --- |
| Exit 3 | One line: the class data isn't responding, I'll try again next check. Do not guess seats. |
| Exit 4 | Say seat data is unavailable right now and stop checking until it is fixed. Do not guess. |
| Exit 5 | Nothing is watched; offer to start a watch. |
| Exit 6 | Class or course not found; ask them to re-pick. |
| Exit 2 | Bad command; fix it and run it again once. |
| Calendar not connected | Ask for the days and times of their other classes, or alert without a schedule check and say so. |
| `WARN ... set aside` | The saved watches were damaged; tell the student they need re-adding and offer to do it. |

## Safety

- Only the student's yes starts a watch, a check-in or a call preference. Say what is watched.
- Never enroll, drop, swap or pay for the student, and never ask for or type a password. The student signs in and makes
  the final click.
- Data goes only to the school's public class search. Nothing about the student is sent anywhere.
- Cubbie texts and calls only its own student.
- Never promise they will get the seat. Seats go fast and some are reserved.
