# Cadence tests (for the team, not for Cubbie to follow)

The open question: how fast can Cubbie tell a student a seat opened? Not part of the student-facing Skill.

Questions to answer on a real Cubbie:

1. What is the shortest recurring check-in interval? Try asking for 1 minute, then 5.
2. Can a check-in run `python3 scripts/seat_sniper.py check`, and end without texting when it prints `NO CHANGE`?
3. Can a check-in place a phone call only when the script reports a change?
4. Can a long-running command (`python3 scripts/seat_sniper.py loop --interval 30 --max-minutes 55`) run in the
   background, and does Cubbie message the student when it prints a line and exits with code 10? (`loop` is a test
   helper: it polls inside one process and returns on the first change.)
5. How long does a seat stay open after it opens? Watch several genuinely closed sections for a day and note it.

Fast self-test without waiting for a real seat: edit your own state file (path in `SEAT_SNIPER_STATE`, default
`~/.config/seat-sniper/state.json`) and set a watch's `last_kind` to `null` while the section is open, then run
`check`. It will report the transition exactly as a real opening would.
