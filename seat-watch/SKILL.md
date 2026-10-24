---
name: seat-watch
description: Watches full class sections and tells the student the moment a seat opens, checked against their schedule. Use only when a student says a class or section is full, or asks to be told when a seat opens. Not for general registration questions.
---

# Seat Watch

Registration is the one week a year a student checks a class page every few minutes. This Skill does the checking:
it watches the sections the student needs, and when a seat opens it says exactly what to do about it, including any
time conflict with their schedule and any linked lab or recitation they also need.

It never enrolls, drops, pays or signs in for the student. It tells them, and they act.

## When to use

- "CSE 310 is full, can you tell me if a spot opens?"
- "I need any section of CHM 116 that doesn't clash with my job."
- "Watch this class for me" (with a class number).
- "Check my watched classes now."

Do not use it for how registration works, what to take, degree planning or waitlist rules. Answer those normally.

## Setup

None. The script uses only the Python standard library. Run it from this Skill's folder.

## Schools

- **ASU** is built in. Use the commands below as written. ASU's term code is a 4-digit number (Spring 2027 is `2271`).
  If the student does not know it, use the term of the registration they are talking about; if still unsure, ask.
- **Any other school** is best effort. Find the school's public class search page with the web or browser ability, read
  the status of the watched sections, and write them to a small JSON file (see `references/other-schools.md`), then run
  `check --rows <file>`. Tell the student this school is not tested and a wrong alert is possible.

## Steps: start a watch

1. Find out what the student needs. Ask one question at a time and suggest a default:
   - Which course and term? (default: the upcoming term)
   - Any section, or one specific section?
   - Which of their current classes could move? (Remember the answer with Cubbie's memory so they are not asked again.)
2. List the sections. Keep it short; filter with `--status closed` (full ones worth watching) and `--comp LEC`:

   ```bash
   python3 scripts/seat_watch.py lookup --term 2271 --subject CHM --number 116 --comp LEC --status closed
   ```

   Send at most five lines, in plain text. Let the student pick.
3. Save the watch (at most 5 at a time):

   ```bash
   python3 scripts/seat_watch.py watch add --term 2271 --subject CHM --number 116 --class 16222
   ```

   If the output says the section is already enrollable, tell the student right away and go to "When a seat opens".
4. Agree on how often to check, then create a recurring check-in. Suggest every hour, and every 5 minutes on the day and
   hour the student's registration opens if Cubbie allows that often. Create the check-in only after the student says yes.
   Word it so it makes sense days later: "Run the seat-watch Skill's check command and message the student only if it
   reports a change."
5. Confirm in one short line what is watched and how often.

## Steps: every check

Read the student's calendar and remembered classes first, and write their commitments to a small JSON file
(`references/busy-format.md`). Then run:

```bash
python3 scripts/seat_watch.py check --busy busy.json
```

- Output `NO CHANGE`: **send the student no message at all.** Do not say "nothing changed". A Skill that texts every
  hour gets uninstalled.
- Exit code 10, with lines starting `EVENT` and `SUMMARY`: go to "When a seat opens".
- Anything else: see "When something fails".

The student can also say "check now". Run the same command and answer, even when nothing changed (then say so in one line).

## When a seat opens

The `SUMMARY` line has the facts. Send one message, not two. Lead with the answer, plain text, short lines. Include:

- the course, class number, days and time, and how many seats are left
- the linked lab or recitation they also need, with its class number and time (the script only alerts when both can be taken)
- any conflict, named
- the caveat line if present (reserved seats or instructor consent: the seat may not be open to them)

If there is a conflict, offer a **swap**, never a drop. In MyASU a swap only removes the old class if the new one is
added, so the student cannot end up with neither. Say it like: "Swap ENG 101 for it?"

When they say yes, send the class numbers on their own lines so they can copy them, and the link to MyASU's enrollment page
(`https://my.asu.edu`). Tell them to sign in and finish the swap themselves. If they ask, open the page in Cubbie's
browser, stop at the sign-in, and hand the browser to them for the password and Duo. Never ask for a password in the chat.

Then ask whether they got in. When they say yes, stop that watch:

```bash
python3 scripts/seat_watch.py watch remove --class 16222
```

If a watch's enrollment deadline passes, the script says so once and removes it; tell the student in one line.

## Replies

Short messages, plain text, no Markdown, one idea each. Put links on their own line. Never state a seat count or a time
the script did not print. If something is uncertain, say so in one line.

Example:

```text
Seat opened: CHM 116 lec, class 16222, MWF 8:00-8:50. 1 seat left.
It needs a lab too: class 16224, Thu 8:00-10:45, 15 seats.
Clash: your ENG 101 (MWF 8:00). Swap it for this?
```

## When something fails

| Result | Meaning | What to text |
| --- | --- | --- |
| Exit 0, `NO CHANGE` | Nothing new | Nothing (unless the student asked "check now") |
| Exit 3 | School's class data unreachable | One line: the class data isn't responding, I'll try again next check. Do not guess seats |
| Exit 4 | The data's format changed | Say seat data is unavailable right now and stop checking until it is fixed. Do not guess |
| Exit 5 | Nothing is watched | Offer to start a watch |
| Exit 6 | Class number not found | Ask them to re-pick from the list |
| Exit 2 | Bad command | Fix the command and run it again once |
| Calendar not connected | No schedule to check against | Ask for the days and times of their other classes instead, or alert without a conflict check and say so |

## Safety

- Only the student's yes starts a watch or a check-in. Say what is watched and how often.
- Never enroll, drop, pay or log in for the student.
- Data goes only to the school's public class search page. Nothing about the student is sent anywhere.
- Never promise they will get the seat. Seats go fast and some are reserved.
- A simulated replay (`check --sample`) is for demos and must be labeled simulated everywhere it is shown.
