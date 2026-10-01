from summary import summarize

result = summarize("method,seed,status,score\na,0,success,1\na,1,failed,\n")
assert result == {"a": {"attempted": 2, "succeeded": 1, "failed": 1, "mean": 1.0, "stdev": None}}
print("Smoke check passed")
