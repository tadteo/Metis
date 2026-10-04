# Provider streaming independent review

Base a21841f; reviewer agent streaming_review reviewed the isolated branch and real
transport, ledger, privacy and interface paths without paid calls.

Two actionable findings were reproduced and corrected:
- Interim cumulative usage followed by disconnect cannot settle as exact; failed
  streams use at least the conservative estimate and explicitly mark it estimated.
- Independently redacted text fragments can leak a secret across chunk boundaries;
  progress now contains metadata only, and the accumulated answer is redacted once
  on completion/interruption. Metadata-only traces continue to omit text.

Named regression tests cover both. Independent re-review approved with 30 targeted
checks passing. Scope limits remain explicit: no historic late-response recovery,
no percentage-complete signal, no deferred polling, and no guarantee of preserving
in-memory partial text through abrupt process death. These do not imply scientific
capability. Later typing-only callback annotation changes retain the same behavior.
