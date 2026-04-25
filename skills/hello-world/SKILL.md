---
name: hello-world
description: Greet the user by name and demonstrate the skill activation mechanism. Use when the user says hello, hi, 你好, or explicitly asks to test the skill system.
---

# Hello World Skill

This skill exists to verify that skill activation and bash execution work correctly.

## How to use

1. Extract the user's name from their message (default to "朋友" if not given).
2. Run the greeting script:

       bash: python skills/hello-world/scripts/hello.py "<name>"

3. Return the script's output to the user.

## Example

User: "你好，我叫明明"
Action: `python skills/hello-world/scripts/hello.py "明明"`
Output: `你好，明明！czon Agent 已经正常运作。`
Response to user: 你好，明明！czon Agent 已经正常运作。
