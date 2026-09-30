# Independent review: automatic project file selection

Base: `cbdd55c`. Reviewer: independent read-only `/root/review` agent.

The reviewer found two actionable issues in the initial diff:

1. Review labelled raw `project.include` globs as files Metis would copy. Normal
   defaults displayed `*` and `**/*`, and escaped literal names were misleading.
   Resolved by returning a bounded preview of resolved filenames and the total
   count from shared preflight. The browser displays filenames, not rules.
2. A partially matching old include list could pass the source check while hiding
   configured training/evaluation scripts. Resolved by detecting existing command
   scripts outside the selection, invoking recovery for their missing-file check,
   and surfacing an actionable folder limit if bounded recovery cannot finish.

The reviewer checked the final diff and reported no remaining actionable findings.
The reviewer did not run tests or visual/keyboard checks; implementation validation
and visual evidence are recorded in the task plan. This review is of software
behavior, not evidence of scientific parity with ScientistTwo.
