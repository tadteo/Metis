# Independent review: blocked-run guidance

Base 236da46. recovery_review independently approved the browser-only fix and ran
all browser suites: 100 passed. Raw errors and model names remain text nodes;
model attribution uses recorded events rather than mutable settings. No provider,
scientific, retry, budget or pinned runtime changes were found.

Finding resolved: Technical details initially lacked the existing raw-details
class, allowing long errors to overflow. The class now supplies wrapping/scrolling.
Adverse cases cover 503, 401/403, unknown/HTML-like errors, missing model evidence,
and an active retry displaying the prior failure without claiming a new stop.

Implementer visual verification: production renderer and styles in a synthetic
fixture at desktop and 390px widths, cream and charcoal. Labels and links wrap;
Enter expands Technical details with visible focus. No private data in fixtures.
