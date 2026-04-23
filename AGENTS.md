# SOVEREIGN OS — Sub-Agent Guide for Claude Code

## How to use Claude Code sub-agents on this project

Claude Code can spawn parallel sub-agents to build multiple modules simultaneously.
This file tells you exactly how to prompt Claude Code to do that correctly.

---

## Starting your session (Person 1 — Project Lead)

Open your terminal in the sovereign-os/ directory and start Claude Code:
```bash
claude
```

Then paste this exact prompt to initialize the sub-agent build:

```
You are building SOVEREIGN OS, an AI companion desktop app.
Read CLAUDE.md first. Then read shared/types.py and shared/config.py.
Then read .claude/tasks/person1_brain_persona.md.
Follow the task file step by step. 
Do not modify any files outside core/, persona/, ui/, and main.py.
After each step, confirm it works before proceeding to the next.
Use sub-agents for any task that can run in parallel.
```

---

## Starting your session (Person 2 — Eyes/Hands/Voice)

```
You are building SOVEREIGN OS, an AI companion desktop app.
Read CLAUDE.md first. Then read shared/types.py and shared/config.py.
Then read .claude/tasks/person2_eyes_hands_voice.md.
Follow the task file step by step.
Do not modify any files outside voice/, vision/, and hands/.
After each step, verify the module test passes before moving on.
```

---

## Starting your session (Person 3 — Memory/Integrations)

```
You are building SOVEREIGN OS, an AI companion desktop app.
Read CLAUDE.md first. Then read shared/types.py and shared/config.py.
Then read .claude/tasks/person3_memory_integrations.md.
Follow the task file step by step.
Do not modify any files outside memory/ and integrations/.
After each step, verify the module test passes before moving on.
```

---

## How sub-agents work in Claude Code

Claude Code spawns sub-agents automatically for parallelizable tasks.
You can also explicitly request it:

```
Use sub-agents to simultaneously:
1. Test vision/eyes.py
2. Test hands/hands.py  
3. Install voice dependencies
Run all three in parallel and report back when all complete.
```

---

## Error handling prompts

If a module fails to import:
```
The import failed. Read the error carefully.
Check if the missing package is in requirements.txt.
If yes, install it. If no, add it with the correct pinned version.
Then retry the import.
```

If a test fails:
```
The test failed. Do not move on.
Read the error message.
Fix the root cause in the module file.
Re-run the test.
Only move to the next step when this test passes cleanly.
```

If there's a merge conflict:
```
There is a merge conflict in [filename].
Read both versions.
Keep the version that matches shared/types.py interfaces.
Do not invent new data shapes.
Resolve and commit.
```

---

## Daily sync checklist

Every morning before starting:
```bash
git pull origin main
pip install -r requirements.txt
python -c "from core.brain import Brain; from vision.eyes import Eyes; from hands.hands import Hands; print('All imports OK')"
```

If any import fails, fix it before writing new code.

---

## Final integration prompt (run after all PRs are merged)

```
All three modules are now merged into main.
Read main.py completely.
Run: python main.py
In a new terminal run: cd ui && npm run tauri dev
Test the following sequence:
1. Type "hello" — verify orb responds and speaks
2. Type "what's on my screen" — verify screenshot + response
3. Type "open Chrome" — verify Chrome opens
4. Type "search for today's weather" — verify web search result
If all four work, SOVEREIGN OS is complete.
```
