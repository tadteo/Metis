"""Credential-free file client for an operator-started Metis decision service.

Copy this file into the research project. Docker networking remains disabled.
"""

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def decide(
    model: str,
    prompt: str,
    *,
    sample: str,
    system: str = "Return a JSON object with your decision.",
    max_output_tokens: int = 512,
    timeout: float = 240,
) -> dict[str, Any]:
    """Return a receipt, including failures; use a new sample for a deliberate retry.

    Reusing identical inputs/sample reuses the recorded attempt, even in a new
    workspace. Such a replay is not a fresh stochastic measurement or free API call.
    """
    request = {
        "model": model,
        "prompt": prompt,
        "sample": sample,
        "system": system,
        "max_output_tokens": max_output_tokens,
    }
    encoded = json.dumps(request, sort_keys=True, ensure_ascii=True, allow_nan=False)
    key = hashlib.sha256(encoded.encode()).hexdigest()
    queue = Path("metis-inference")
    queue.mkdir(exist_ok=True)
    response = queue / (key + ".response.json")
    response.unlink(missing_ok=True)  # Controller journal, not this copy, owns the receipt.
    temporary = queue / (uuid.uuid4().hex + ".tmp")
    temporary.write_text(encoded)
    os.replace(temporary, queue / (key + ".request.json"))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if response.exists():
            result = json.loads(response.read_text())
            if result.get("request_id") != key:
                raise ValueError("Decision response identity mismatch")
            return result
        time.sleep(0.2)
    raise TimeoutError("No decision receipt; preserve the request and inspect the controller")
