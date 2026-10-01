"""Independent acceptance suite; never copied into the agent's input workspace."""

import json
import math
import statistics
import sys
import unittest

from summary import summarize

HEADER = "method,seed,status,score\n"


class Acceptance(unittest.TestCase):
    def test_empty_and_failed_only(self):
        self.assertEqual(summarize(HEADER), {})
        self.assertEqual(
            summarize(HEADER + "a,0,failed,\na,1,failed,\n"),
            {"a": {"attempted": 2, "succeeded": 0, "failed": 2, "mean": None, "stdev": None}},
        )

    def test_counts_and_sample_statistics(self):
        result = summarize(HEADER + "a,0,success,1\na,1,failed,\na,2,success,3\nb,0,success,-4\n")
        self.assertEqual(set(result), {"a", "b"})
        self.assertEqual(set(result["a"]), {"attempted", "succeeded", "failed", "mean", "stdev"})
        self.assertEqual([result["a"][k] for k in ("attempted", "succeeded", "failed")], [3, 2, 1])
        self.assertEqual(result["a"]["mean"], 2)
        self.assertAlmostEqual(result["a"]["stdev"], math.sqrt(2))
        self.assertEqual(
            result["b"], {"attempted": 1, "succeeded": 1, "failed": 0, "mean": -4, "stdev": None}
        )

    def test_csv_and_whitespace(self):
        result = summarize(
            ' method , seed , status , score \n\n" a,b\nx ", 01 , success , 2.5 \n\n'
        )
        self.assertEqual(
            result,
            {"a,b\nx": {"attempted": 1, "succeeded": 1, "failed": 0, "mean": 2.5, "stdev": None}},
        )

    def test_invalid_header(self):
        for text in (
            "",
            "\n",
            "method,seed,status\n",
            "method,status,seed,score\n",
            "method,seed,status,score,extra\n",
            "method,seed,score,score\n",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                summarize(text)

    def test_invalid_records(self):
        for row in (
            "a,0,success",
            "a,0,success,1,x",
            ",0,success,1",
            " ,0,success,1",
            "a,-1,success,1",
            "a,1.0,success,1",
            "a,+1,success,1",
            "a,١,success,1",
            "a,,success,1",
            "a,x,success,1",
            "a,0,unknown,1",
            "a,0,Success,1",
            "a,0,success,",
            "a,0,success,nan",
            "a,0,success,inf",
            "a,0,success,-inf",
            "a,0,success,1e999",
            "a,0,success,bad",
            "a,0,failed,0",
            "a,0,failed,nan",
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                summarize(HEADER + row + "\n")

    def test_duplicate_normalized_identity(self):
        for row in ("a,1,success,3", " a ,01,failed,"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                summarize(HEADER + "a,1,success,2\n" + row + "\n")

    def test_numerical_accuracy(self):
        for values in ([1e12 + 0.1, 1e12 + 0.2, 1e12 + 0.4], [1e10, 1, -1e10, 2], [0, 0, 0]):
            text = HEADER + "".join(f"a,{i},success,{x}\n" for i, x in enumerate(values))
            result = summarize(text)["a"]
            self.assertTrue(
                math.isclose(result["mean"], statistics.mean(values), rel_tol=1e-12, abs_tol=1e-12)
            )
            self.assertTrue(
                math.isclose(
                    result["stdev"], statistics.stdev(values), rel_tol=1e-12, abs_tol=1e-12
                )
            )


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance)
    )
    print(
        "PONYTAIL_ACCEPTANCE "
        + json.dumps(
            {
                "tests": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
            }
        )
    )
    sys.exit(0 if result.wasSuccessful() else 1)
