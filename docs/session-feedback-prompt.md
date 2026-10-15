# nix-agent session feedback

Review your use of nix-agent during this session and provide candid feedback for its maintainer. Base your report on actual calls, outputs, and decisions in this session. Do not run additional builds, activations, rollbacks, or experiments for this review.

Include:

1. Context and outcome
   - What task were you doing?
   - Was this NixOS, integrated Home Manager, or standalone Home Manager?
   - Which nix-agent tools did you use?
   - If none were used, were tools exposed but unnecessary, absent from the session's tool catalog, or never checked? Use existing session evidence; do not infer availability from an installed skill or server process.
   - State when the reviewed calls occurred and the nix-agent version/source revision if already known. Distinguish retrospective observations from tests of the current checkout.
   - What did you complete, and what remains unverified? Distinguish evaluation, build, activation, and observed runtime behavior.

2. What helped
   - Which outputs directly helped you make a decision or complete the task?
   - Did structured errors, package diffs, option locations, batched evaluation, or health summaries save work?
   - Give concrete examples. Do not invent time or token savings.

3. Problems and friction
   - Report failures, confusing behavior, missing information, excessive output, or truncation that hid useful details.
   - For each issue, include the tool and relevant arguments, a short output excerpt, expected behavior, actual behavior, and your workaround.
   - Distinguish suspected nix-agent bugs from configuration errors, missing dependencies, permissions, MCP host restrictions, or uncertainty.
   - Mention any shell commands or other tools you needed instead, and why.

4. Operational behavior, if exercised
   - Were target resolution and NixOS/Home Manager mode selection clear?
   - Were privilege errors, activation health, and rollback instructions actionable?
   - If you rolled back, did it restore the intended generation and behavior?
   - Mark unused features as "not exercised."

5. Improvements
   - Rank up to three changes by their impact on this session.
   - For each, explain the concrete problem and the smallest useful fix.
   - Include opportunities to simplify or remove unnecessary behavior.

Keep the report concise, with enough evidence to reproduce significant issues. Separate observations from hypotheses. Redact secrets and private URLs. If everything worked, say so without manufacturing complaints.

Save the report as Markdown in:

`/home/rupan/projects/nix-agent/feedback/sessions/`

Create the directory if needed. Use a unique filename:

`YYYY-MM-DDTHH-MM-SSZ_<agent>_<task-slug>.md`

Use the current UTC timestamp, your agent name, and a short description of the task. Never overwrite an existing report. Include the report date and your model/version if known.

Write only this report. Do not modify source files, commit changes, or submit issues. In your final response, link to the saved report and state the most useful finding in one sentence.
