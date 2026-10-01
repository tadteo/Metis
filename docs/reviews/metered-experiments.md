# Independent review: metered experimental decisions

Reviewed against d67c522 by the independent metered_review agent. Final verdict:
approved; the reviewer independently ran the focused suite (18 passed).

Reviewed shared budgeting, one-attempt accounting, interrupted-call recovery without
resending, credential isolation, path/symlink boundaries, process exclusion and stale
response recovery. Findings corrected before approval: deep JSON could interrupt
polling; an unsafe budget-response path could escape its exception handler; a stale
paused response could mask resumed access; source hashes needed archived source
bytes. Regression checks cover those cases and concurrent service exclusion.

No claim of scientific validity, provisioned Laya dependencies, or completed writer
integration follows from this review. Operator access checks remain separate from
scientific measurements. Runtime/configuration fingerprints remain unchanged.
