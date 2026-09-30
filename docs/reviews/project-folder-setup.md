# Independent review: project folders and setup disclosure

Base: `a367ffb`. Reviewer: independent agent `/root/review_folder_setup`, read-only.
Reviewed implementation, tests, scientific readiness boundaries and repository workflow.

Initial findings (all P2):
- Readiness preparation/retry actions left the new parent inspection disclosure closed.
- Source diagnostics incorrectly redirected to the advanced experiment section.
- Automatic folder creation failures could be invisible outside the Project section.

Resolved by opening the parent disclosure, separating source versus experiment-field
navigation, and reporting folder creation failures through the shared setup error.
Regressions cover the latter and inspection disclosure. During primary visual QA,
long directory names overflowed the narrow picker; scoped min-width and text wrapping
fixed the issue. Both themes now measure equal dialog client/scroll widths (352px).

Final independent re-review: all three findings resolved, no remaining blocking
findings. Reviewer independently ran 83 passing browser tests. Authenticated route
coverage reviewed: listing, invalid input, unique creation, preserving existing files,
no run creation, and rejection of a linked managed parent. HTTP and visual evidence
were gathered by the primary agent, not independently repeated by the reviewer.

No scientific stage, evaluator protection or measured-evidence gate was changed.
Folder creation alone does not implement autonomous research project bootstrapping.

Combined-source review at `3cbbce9` after main's navigation integration: approved,
no new interaction regressions. Home reload prevention and theme-label linkage are
preserved; folder disclosure, setup entry and responsive fixes remain intact.
