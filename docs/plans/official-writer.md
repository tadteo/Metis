# Official writer integration verification

Base: current main after the honest import and reviewed workflow gates.
Status: implementation and independent review.

## Plan

1. Preserve the pending official-writer work from the pre-existing integration chat as a focused
   branch. Its development began before this repair; do not misrepresent it as newly authored here.
2. Verify the bridge runs pinned official PaperOrchestra agents and retains their topology,
   prompts, plotting, compilation, references, usage, failures and resumable artifacts.
3. Audit integration correctness independently, repair findings and add regression tests.
4. Exercise actual pinned upstream code where possible without paid model credentials; label
   injected transport responses honestly. Record any external evaluation prerequisite.
5. Commit this coherent integration delta after review, then merge when the original checkout's
   concurrent edits have been reconciled.

Source: https://github.com/google-research/paper-orchestra at
`ca1b3fa01c2970fc7cda32d16245db38d57b3f56` (Apache-2.0).

Scope: PaperOrchestra bridge/worker/setup, container environment, writing dispatch, focused tests
and integration documentation. Separate branches own claim integrity and engine history.
