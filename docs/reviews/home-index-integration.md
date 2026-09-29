# Preserved Home inquiry edit

The user requested merging the compact SSH picker together with the existing uncommitted Home edit in `src/autoresearch/static/index.html`. The Home edit removes the extra guide button and visible field label, and changes the question placeholder. Its intent and constraints are recorded in `docs/plans/inquiry-form-reset.md`; the picker has its separate plan and review. This record preserves the Home edit as a distinct commit before merging the picker branch into `main`.

An independent read-only review found one accessibility issue in the original Home edit: after visible label text was removed, the textarea had no concise accessible name. The edit now gives it `aria-label="Write your research question"` and associates the existing status hint with `aria-describedby`. The reviewer confirmed that the guide remains reachable through the sidebar, the optional Home guide listener is guarded, and the Home and picker changes affect separate regions of the page. No blocking finding remained.

Before the Home commit, `node --test tests/test_web_ui.mjs` passed 53/53, including the missing-guide regression, and `git diff --check` was clean. Combined post-merge browser and repository checks are recorded in `docs/reviews/remote-picker-implementation.md`.
