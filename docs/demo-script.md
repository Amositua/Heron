# Demo Script

Target runtime: under 3 minutes. Record after running `python -m scripts.stage_demo`
from `backend/`, which leaves the system in the state this script assumes.

## 0:00 - 0:15 - Title card

- Title card: "Heron — the Splunk app that builds and maintains itself."
- Cut to the Changelog view for `payments_pod_monitoring`.

## 0:15 - 0:45 - Lead with the maintenance cut

- "Two weeks ago, I asked Heron to monitor pod restarts in our payments namespace.
  Here's what it's done since, on its own."
- Zoom into the auto-tuned changelog entry (timestamped ~10 days ago).
- Read the rationale aloud: the alert was firing on every noisy restart burst, so
  Heron raised the threshold and explained why in plain language.
- Point out the before/after diff in the expanded entry.

## 0:45 - 1:30 - How Heron got here

- "Here's how Heron built this in the first place."
- Switch to the Chat view. Type the original prompt:
  > "I need to monitor pod restart spikes in our payments namespace. Alert me when
  > there are more than 5 restarts in 10 minutes for any pod in that namespace."
- Submit and cut to the Build view.
- Let the SSE stream play: stage progression (planning -> generating -> deploying
  -> validating -> done), generated files appearing in the file tree, the MCP
  deploy actions, and the validation checklist going green.
- Land on the "build complete" banner linking to the deployed app.

## 1:30 - 2:15 - The maintenance loop in action

- "Once deployed, Heron stays attached to the app."
- Narrate the Observer -> Tuner -> Approver pipeline using the same run that
  produced the changelog entry shown at 0:15: noisy restart data triggers the
  alert repeatedly, the Observer reports the firing frequency, the Tuner proposes
  a higher threshold with a written rationale, and the Approver auto-applies it
  because it's a low-risk threshold nudge.
- Show the Approvals view briefly to contrast: this change was low-risk and
  auto-applied, but higher-risk changes (SPL rewrites, new panels) would land
  here for human sign-off instead.

## 2:15 - 2:45 - Reversible and audited

- "Every change Heron makes is reversible, and every action is audited."
- Back in the Changelog view, click "Rollback to before this change" on the
  auto-tuned entry and show the threshold revert in real time.
- Briefly show the MCP audit log entries from the Build view's deployment step
  as evidence that every Splunk write went through the MCP Server.

## 2:45 - 3:00 - Close

- Cut to the architecture diagram (`architecture-diagram.png`).
- Closing line: "An autonomous engineer for Splunk apps. Built for the Splunk
  Agentic Ops Hackathon."
