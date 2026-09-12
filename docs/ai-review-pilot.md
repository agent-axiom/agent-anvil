# AI review pilot

Pilot scope: 10-20 code-changing pull requests in
`agent-axiom/agent-anvil`. CodeRabbit is the primary PR reviewer, Codex reviews
complex changes on request, and Sourcery reviews a selected comparison cohort.
All findings are advisory. Existing CI and maintainer approval remain the merge
criteria.

## Configuration and activation

`AGENTS.md` contains shared review rules for Codex and CodeRabbit.
`.coderabbit.yaml` configures CodeRabbit after its GitHub App is installed.
These files do not install GitHub Apps or enable Codex cloud review.

Installations and settings must be scoped to `agent-axiom/agent-anvil`.
Use OSS access for CodeRabbit and Sourcery. Leave paid add-ons disabled.
Do not add AI review checks as required branch checks during this pilot.

### CodeRabbit

1. Sign in at [CodeRabbit](https://app.coderabbit.ai/) and install its GitHub App
   for `agent-axiom/agent-anvil` using selected-repository access.
2. Confirm OSS access and that the repository uses `.coderabbit.yaml`.
3. CodeRabbit reviews non-draft PRs automatically when the OSS tier permits it.
   Under the current [OSS limits](https://docs.coderabbit.ai/management/plans),
   public repositories with fewer than 10 stars require manual review.
4. Request a review with `@coderabbitai review`, or a complete pass with
   `@coderabbitai full review`. Automatic incremental reviews are disabled to
   limit repeated comments and quota use; request another review after fixes.
5. Check the first walkthrough/status message for configuration errors or
   review limits. The title marker `[skip ai review]` skips automatic review.

Ruff runs in CI, so its duplicate CodeRabbit integration is disabled. Runtime
code, tests, schemas, contract fixtures, and workflow changes remain in scope.
Generated run/report output and build artifacts are excluded from the diff
review. Changes to code that produces or publishes those artifacts remain in
scope. Shared rules are discovered from root `AGENTS.md`.

### Codex

1. Open [Codex code review settings](https://chatgpt.com/codex/settings/code-review)
   with the ChatGPT account connected to the repository.
2. Set up a Codex cloud environment for the repository if needed, then enable
   Code review for this repository. Leave Automatic reviews off for the pilot.
3. On complex changes, request `@codex review`. Example focus:
   `@codex review for evidence trust, contract compatibility, and false passing evaluations`.
4. Confirm that Codex acknowledges the request and posts a review or completion
   reaction. A connected GitHub App alone does not establish active PR review.

GitHub review and local review use the applicable
[Codex plan limits](https://learn.chatgpt.com/docs/pricing).
[Repository rules and setup](https://learn.chatgpt.com/docs/third-party/github)
describe how root and nested `AGENTS.md` files guide reviews.

### Sourcery

1. Sign in at [Sourcery](https://app.sourcery.ai/) and install its GitHub App
   for this repository only; confirm the Open Source plan.
2. In Repo settings, select `agent-axiom/agent-anvil`, disable Use Organization
   Settings, and keep Enable Sourcery on pull requests and AI review comments on.
3. Set profile to Quiet and language to English. Disable PR summaries, review
   guides, sequence diagrams, and tips. Keep draft review off.
4. Set the Labels allowlist to `ai-review-compare`. Add that label only to
   selected comparison PRs. This permanent cohort label is distinct from
   Sourcery's temporary `sourcery-review` command label.
5. Add the rule below under Review rules with path pattern `**`.
6. On selected PRs, use `@sourcery-ai review` to request a fresh full pass and
   confirm a completed response. Do not use the top-level disable switch for
   selection: it stops Sourcery from posting anything on PRs.

Sourcery's current documented configuration is in
[Review settings](https://docs.sourcery.ai/reviews/configure/) and
[Review rules](https://docs.sourcery.ai/reviews/review-rules/).
The block below is ready for the Rule field; it is not automatically loaded
from this document. Keep its scope repository-specific.

```text
Report concrete defects introduced by the change, with the triggering input,
actual behavior, and impact. Prioritize false passing evaluations, broken
contracts, evidence trust regressions, and accidental disclosure. Omit style
preferences, speculative refactors, and duplicate lint/type-check findings.

Preserve trace completion and CLI exit semantics. Missing final output,
malformed protocol events, timeouts, and failed external processes must not
silently become successful evaluations. The refund regression scenario is an
intentional failure; do not report its unsafe demo behavior as a harness bug.

Check model changes against public JSON/YAML schemas, fixtures, and JSONL/HTTP
consumers. Schema-valid or self-declared trust is not verified evidence. Review
content digests, release bindings, parent graphs, store containment, and pack
registration. Contract data must not drive dynamic imports. Explicit legacy
JSON schemas intentionally retain their documented unbounded-size behavior.

External agent and MCP commands are explicitly trusted inputs, not sandboxed
code. Flag introduced execution and permission regressions, not this documented
feature. Local raw traces are intentional; outbound grader payloads are
redacted by default and leaderboard submissions contain aggregates. Flag new
credential leaks or unintended publication of raw traces. Offline grading must
not unexpectedly send grader payloads to OpenAI.
```

Command details: [Sourcery commands](https://docs.sourcery.ai/reviews/commands/).

## Sampling and measurement

Use the first 10 qualifying PRs after activation. Exclude generated-only,
documentation-only, and version-only PRs. Extend to at most 20 if the initial
sample does not cover evaluation logic, adapters, contracts, and evidence.

Compare Sourcery on at least five of these PRs, covering both ordinary and
complex changes. Request Codex on complex changes in that cohort. Record the
same head SHA for comparisons and run reviewers before applying fixes. If the
head changes between reviews, treat the results as different samples.

Log one row per reviewer and head SHA. A defect is confirmed only after a
maintainer establishes its triggering path or reproduction. Count duplicate
reports of the same defect once per reviewer. A finding is unique only when
the other reviewers that completed that same sample did not report it.
Rate-limited, unavailable, and incomplete reviews are not zero-finding reviews.

| PR / head SHA | Reviewer | Completion | Confirmed defects | Unique defects | False positives | Triage minutes | Finding/fix links |
| --- | --- | --- | --- | --- | --- | --- | --- |

No measurements have been recorded yet. Add rows as the pilot runs.

After 10 qualifying PRs, compare confirmed defects, incremental unique defects,
and triage time. Keep a secondary reviewer only when its additional useful
findings justify the time spent. An empty sample is not evidence of quality.

## End or pause the pilot

At the 10-PR checkpoint, explicitly decide whether to stop or extend to 20.
This count is a maintainer checkpoint, not an automatic scheduler.

To pause CodeRabbit, set `reviews.auto_review.enabled: false`; manual review
remains available. To stop Sourcery sampling, stop adding `ai-review-compare`
and remove it from still-open sample PRs, or disable Sourcery for this repository.
Codex remains on demand. Review or revoke repository access for a service that
is no longer used.
