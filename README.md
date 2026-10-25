<div align="center">

<img src="assets/hero.webp" alt="It's Done Bro. Get the right seat before someone else does. A student texts Cubbie to watch CSE 340, then gets a text when a seat they can take opens, and a call if they miss it." width="100%">

<img src="assets/steps.svg" alt="Text it. Forget it. Get the text." width="100%">

<img src="assets/install.svg" alt="Start with one text. Text Cubbie the link https://github.com/HimJar911/its-done-bro, reply yes, then say Watch CSE 340 for me." width="100%">

<img src="assets/compare.svg" alt="A plain seat alert only says a seat opened. It's Done Bro says the lab is open, it fits your schedule, nothing restricts it, and a backup is ready." width="100%">

<img src="assets/checks.svg" alt="Five checks before it texts you: the seat is real, the lab is open too, it fits your week, no strings attached, and there is a backup." width="100%">

<img src="assets/chat.svg" alt="Three short chats with Cubbie: watch only one professor's sections, ask why a section wasn't mentioned, and pause the watch for an hour." width="100%">

<img src="assets/control.svg" alt="You stay in control: it never enrolls you, never drops a class, never asks for a password, calls only if you opt in, lets you snooze or acknowledge, and stops on its own." width="100%">

<img src="assets/proof.svg" alt="A live lookup of CHM 113 for Spring 2027 showing open labs and one full lab, section by section." width="100%">

<img src="assets/engine.svg" alt="How it works: you text Cubbie, Cubbie runs the Skill, the checker reads the school's public class search and decides, and Cubbie texts you back." width="100%">

</div>

<br>

<details>
<summary><b>How an alert is decided</b></summary>
<br>

Every section of the course is checked on its own, never as one combined total. A section counts as one you can take only when all of this is true:

- the section itself has a seat open
- every lab or recitation it requires also has a seat open
- it doesn't overlap the classes and commitments you've shared
- reserved seats and instructor-consent sections are flagged, not hidden

If something opens but you can't take it, nothing is sent. If another section of the same course works, you hear about that one instead. If a seat you were told about closes again, you're told once.

After a text, if you've said yes to calls and haven't replied within a few minutes, Cubbie calls. Quiet hours (10 PM to 7:30 AM) block calls.

</details>

<details>
<summary><b>Which schools it works with</b></summary>
<br>

It reads a school's public class search, so there's no sign-in and nothing private. It's been tested on live class data from several universities. For a school it can't read directly, Cubbie can copy the sections off the class-search page into a list the checker understands. See `references/schools.md`.

</details>

<details>
<summary><b>Questions</b></summary>
<br>

**Does it register me for the class?** No. It sends you the registration link and you finish it yourself.

**Do I give it my password?** No. It never asks for one.

**What if I miss the text?** If you opted in, Cubbie calls. You can also say "pause it for an hour" or "stop watching it" at any time.

**Can I watch more than one class?** Yes, up to ten at once.

**How do I stop it?** Tell Cubbie you got in, or just say stop. It also ends a watch on its own after 30 days.

</details>

<details>
<summary><b>What's in this repo</b></summary>
<br>

| Path | What it is |
| --- | --- |
| `SKILL.md` | How Cubbie understands, schedules and replies |
| `scripts/its_done_bro.py` | The checker. Standard library only, no installs |
| `references/schools.md` | Setting up a school |
| `tests/` | 11 tests covering the alert logic |

</details>

<br>

<div align="center">

[**Like It's Done Bro? Vote for it →**](https://hackathon.cubbie.ai/#gallery)

</div>
