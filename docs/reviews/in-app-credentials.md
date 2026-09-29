# Independent review: in-app model credentials

Base: `d890295`. Reviewer: independent `credential_review` agent, read-only review of the task branch against `docs/plans/in-app-credentials.md`, development and interface standards. The reviewer inspected the credential resolver, authenticated web route, browser form, provider, trusted model adapters, writer worker, and managed SSH path.

## Findings and resolution

- Session storage initially left an older vault key in place, so it could reappear after restart. Saving a session key now deletes a reachable vault entry first. When the vault cannot be reached, Metis explicitly says an older key cannot be checked and may reappear.
- Clear initially claimed success when vault access was unavailable. It now removes the session key and returns a `vault_unverified` result, which the UI explains. If vault deletion fails while accessible, the route reports an error; session memory is still cleared.
- The writer worker initially missed a configured compatible model key named `GEMINI_API_KEY` or `SEMANTIC_SCHOLAR_API_KEY`. It now resolves every configured compatible model name before forwarding only the named keys to the trusted worker.
- The password field initially survived Escape and had `autocomplete="new-password"`. Dialog cancel/close now clears it, and autocomplete is off. Metis does not write browser storage; browser-level password-manager behavior is outside Metis control.
- Accepted keys shorter than eight characters were not covered by known-secret redaction. In-app keys now require at least eight ASCII characters. Environment credentials retain their existing validation path.
- A successful vault write initially could report session storage if the readback failed. Vault writes now require matching readback and return the actual persistence source; failure states that the vault may have saved the entry.
- Vault read errors initially fell back silently to a different environment key. They now fail closed in status, preflight and provider transport with a safe diagnostic, avoiding a paid call under a different account.
- Model key status could remain stale while editing the lookup name. It now marks the status unchecked on input and refreshes on change.
- A final browser-only refinement invalidates earlier setup approval and marks key removal unverified when the credential route errors. The reviewer checked that delta separately; the browser suite passed 49/49 and no new finding remained.
- The reviewer noted that local generated-code execution shares the host user and may access that user's vault. The local execution checkbox and security documentation now state this limitation; Docker remains the default backend.

The final independent pass reported no remaining actionable findings. It confirmed that an SSH console stores the key on the remote server host. Focused Ruff and whitespace checks passed in the reviewer's read-only pass. Deterministic checks and visual observations are recorded in the task plan.
