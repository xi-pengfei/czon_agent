---
name: enterprise-skill-creator
description: Create a new enterprise Agent Skill, modify an installed Skill, or create a new Skill from an existing one. Use for iterative design, testing, validation, and packaging of private business-process Skills for czon_agent.
---

# Enterprise Skill Creator

Help the user create or improve a small, auditable Agent Skill through the normal conversation, attachments, and existing tools. Do not create a separate editor, test engine, database record, or version library.

## Choose The Operation

Infer the operation from the user's request and confirm it only when the target is ambiguous:

- **Create:** Build a new Skill from the user's business process.
- **Modify:** Copy an installed Skill into the draft folder and revise that copy. The installed Skill remains unchanged while drafting.
- **Create from existing:** Copy an installed Skill into a draft with a new name, then adapt it without changing the source Skill.

Use the same draft location for all three operations: `$CZON_WORKSPACE/skill_drafts/<target-skill-name>/`. If a draft for that target already exists, continue it instead of creating another draft location.

## Boundaries

- Keep every draft under `$CZON_WORKSPACE/skill_drafts/<skill-name>/`.
- Never edit, rename, or delete anything directly under the formal `skills/` directory. Read an installed Skill only as the source for a draft.
- Never install or enable a draft. Installation is an authorized Skill-manager action in the existing 技能管理 page.
- Treat the draft folder as the single source of truth. Continue editing the same folder until the user approves it.
- Do not create empty directories, placeholder files, README files, changelogs, database drafts, or version archives.
- Use lowercase letters, numbers, and hyphens for the Skill name. The name must match its directory.

## Discovery

Ask only for information that is still missing. Gather these essentials across a natural conversation:

1. Skill name.
2. Business purpose and the people who will use it.
3. Phrases or situations that should trigger it.
4. Inputs, including uploaded file types and required business data.
5. Outputs and the criteria for a correct result.
6. Enterprise systems involved and a safe example suitable for testing.

Restate the understood workflow before writing files when an important business rule remains ambiguous. Do not force the user through a fixed questionnaire or fixed number of rounds.

## Choose The Minimum Structure

Always create `SKILL.md`. Add another resource only when it has a concrete purpose:

- `scripts/`: deterministic, repeated processing that is more reliable as code.
- `references/`: actual schemas, field mappings, business rules, or API documentation needed on demand.
- `assets/`: templates, lookup data, or static resources used to produce outputs.

Prefer the Agent's existing tools and installed Skills over duplicate code. Keep AI judgment in the Agent conversation. Generated scripts must not call a model provider directly.

Follow the current Agent Skills specification:

- `SKILL.md` starts with YAML frontmatter containing `name` and `description`.
- `name` is 1-64 characters, contains only lowercase letters, numbers, and single hyphens, and matches the parent folder.
- `description` is 1-1024 characters and states both what the Skill does and when to use it.
- Instructions and resource links use paths relative to the Skill root.
- Keep the main instructions concise and move genuinely conditional detail into focused reference files.

## Configuration And Secrets

- Model choice and model credentials come from the system database through the active Agent. Never place model API calls in generated scripts.
- Never read `DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY`, `DASHSCOPE_API_KEY`, or another provider key from a generated Skill.
- Never ask the user to paste a real secret into the conversation.
- Never write a real key, token, password, cookie, or secret into a prompt, log, command, draft file, test fixture, or `SKILL.md`.
- For DingTalk, Kingdee, and other enterprise connections, record only the required environment variable names and explain that an administrator must configure them in the server's `.env` file outside the conversation. Do not invent a value or claim it has been configured.
- Use neutral variable names scoped to the business integration. Do not reuse model-provider variables for business credentials.

## Draft And Check

For a modification, copy `$CZON_PROJECT_ROOT/skills/<source-skill-name>/` into the target draft before editing. For creation from an existing Skill, copy the source and immediately change the target directory name and `SKILL.md` frontmatter name. Never overwrite an existing draft implicitly.

Create or update the draft with the existing file tools. After every meaningful revision, run:

```bash
python skills/enterprise-skill-creator/scripts/validate_skill.py "$CZON_WORKSPACE/skill_drafts/<skill-name>"
```

The check must cover:

- Agent Skills frontmatter and directory naming.
- Unexpected files, symlinks, absolute local paths, and hardcoded secrets.
- Dangerous shell commands and attempts to install dependencies at runtime.
- Python syntax and imported third-party packages.

Show the user the draft path, compact file tree, check results, external dependencies, and unresolved configuration variable names. Fix deterministic errors before asking the user to test.

## Test And Refine

Reuse the normal conversation and its attachments for testing.

1. Label pre-install execution as `草稿试跑`, because the draft is not yet in the formal Skill loader.
2. Read the draft `SKILL.md` and follow it in the current conversation using the existing Agent tools.
3. For scripts, copy user-provided test input into `$CZON_WORKSPACE` during the same turn before testing. Never alter the original upload.
4. Run only non-destructive steps during a draft test. Do not submit records to a real enterprise system unless the user explicitly requests it and the normal tool policy permits it.
5. Compare the result with the stated acceptance criteria, explain any mismatch, revise the same draft, and test again.
6. Make clear that exact activation and permission behavior can only be verified after administrator installation.

Do not declare a Skill ready merely because its files pass static checks. When the Skill contains executable behavior, test one representative normal case and one invalid-input or expected-failure case.

## Package And Install

Only package after the user says the draft is ready and validation succeeds:

```bash
python skills/enterprise-skill-creator/scripts/validate_skill.py "$CZON_WORKSPACE/skill_drafts/<skill-name>" --package "$CZON_WORKSPACE/<skill-name>.zip"
```

Provide the generated ZIP as a browser download link. Then instruct an authorized Skill manager to open 技能管理 and:

- For a new Skill, upload the ZIP, review it, and enable it.
- For a modification, briefly stop the installed Skill and upload the same-name ZIP. The system replaces it safely while keeping it stopped for review, then the manager enables it again.
- For creation from an existing Skill, upload it as a new Skill; the source remains unchanged.

Uploading through the existing page is the explicit confirmation that changes formal `skills/`. When the user confirms installation succeeded or abandons the work, remove the corresponding draft and generated ZIP. Keep no long-term backup.

Finish with this compact summary:

- Skill name and purpose
- Draft path and file tree
- Validation and test result
- Required business configuration names, without values
- Package download link when created
- Remaining Skill-manager action
