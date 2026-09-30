"""Bounded subprocess for untrusted PDF extraction; no network or model credentials needed."""

from __future__ import annotations

import json
import resource
import sys

from pypdf import PdfReader


def main() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    if sys.platform != "darwin":
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    # Darwin rejects address/data limits; the controller supervises resident memory.
    reader = PdfReader(sys.argv[1])
    if reader.is_encrypted or len(reader.pages) > 500:
        raise ValueError("Unsupported encrypted or oversized document")
    pages = []
    remaining = 500000
    for number, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "")[:remaining]
        pages.append({"page": number, "text": text})
        remaining -= len(text)
        if remaining <= 0:
            break
    print(json.dumps(pages))


if __name__ == "__main__":
    main()
