Use the history action to inspect previous steps and their artifact references.
An observation_omitted entry identifies an oversized step by history_step and hash.
Request {"tool":"history","offset":STEP,"limit":1,"start_char":0,"char_limit":4096}
to read its privacy-redacted JSON in bounded character pages. Continue with next_char
until it is null; sha256 identifies this view and original_sha256 identifies the saved
original. Offsets and total_chars refer to the redacted view. The runtime can lower
the requested page size to fit the context allowance. All offsets are zero-based.
Normal history ranges remain available; request pages when a range is oversized.
A page fragment is data, not a complete JSON document or a successful experiment.
