Repeated seeds never establish significance by themselves.
For a paired sign-flip comparison, create statistical_plan.json before the formal
execution. Its exact schema is: {"schema_version":1,"test":"paired_sign_flip",
"metric":"score","pairs":[{"left":"candidate-id","right":"control-id"}],
"alternative":"two-sided","alpha":0.05,"family_size":1,"correction":"bonferroni",
"assumptions":"Explain independent paired units, exchangeable signs, and inference scope."}.
Use 2–20 distinct completed pairs with unique matched seeds, shared protocol,
consistent dataset provenance/units, and homogeneous source hashes per group.
The protected evaluator reads AUTORESEARCH_STATISTICAL_PLAN and
AUTORESEARCH_ANALYSIS_INPUTS. Declare its JSON output in project.analysis_artifacts.
Use the existing generic analysis schema: method="paired_sign_flip", metric,
statistic="p_value" or "effect_size", value, input_experiment_ids, input_fingerprints.
Compute the Bonferroni-adjusted exact sign-flip p-value or mean paired difference.
The host checks arithmetic and pre-execution registration. It does not certify
pre-observation registration, independence, exchangeability, or complete family size.
The claim ledger retains numeric_span/literal values and separate analysis execution
ID. Set statistical_conclusion to significant, not_significant, or estimate.
Explicit significance wording cannot be overridden by estimate. Unvalidated methods
can supply executed values but cannot certify a significance conclusion. Report
planned statistics as p = NUMBER, p < NUMBER (also <=, >, >=), mean difference =
NUMBER, or effect = NUMBER; use separate claim spans for other quantities.
