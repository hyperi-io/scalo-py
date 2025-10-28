# Codex Session Startup Guide

This guide lets a Codex agent reuse the existing-focused AI assets without touching the CI stack.

## 1. Bootstrap the CI tooling
- Run `./ci/bootstrap --install`  
- Run `./ci/ai install`  
- Do not modify files under `ci/` (read-only submodule).

## 2. Load the canonical project context
- Read `STATE.md` in the repository root.
- Open `ci-local/CODE-ASSISTANT.md` and follow every rule.
- Review every file in `docs/standards/` (especially `GIT-WORKFLOW.md` and `CHARS-POLICY.md`).
- Check `TODO.md` for current priorities when it exists.

## 3. Respectassets
- Treat everything under `` as your configuration source (settings, hooks, policies).
- Do not try to regenerate or fork those files; reuse them as-is.
- If you need tier guidance, assume the defaulttier unless the user states otherwise.

## 4. Stay within approved scope
- Never scan or edit `ci/` unless the user explicitly instructs you to.
- Use `.tmp/` for scratch files and keep shell commands simple (avoid `&&`, `||`, `;`, `|` unless strictly required).
- Run tests or build commands through the provided wrappers (e.g., `./ci/run test`, `./ci/run check`).

## 5. Escalation rules
-remains the primary agent. If you hit a policy conflict or need broader access, stop and hand off to thetier.
- Record any questions or blockers in `TODO.md` if asked, then notify the user.

Following these steps keeps Codex aligned with the existing-first workflow while giving it the context it needs to contribute safely.
