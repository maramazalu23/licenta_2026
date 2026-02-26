from __future__ import annotations

from typing import Any, Dict

POLICIES: Dict[str, Dict[str, Any]] = {
    "pcgarage.ro": {
        "strategy": "JS_REQUIRED",     # dacă 403 -> JS imediat
        "timeout_s": 30,
        "min_len": 30_000,
        "must_contain": "/notebook-laptop/",
        "fail_threshold": 1,
        # opțional (dacă vrei override față de HTTP.max_retries)
        # "max_retries": 3,
        # "backoff_base_s": 1.0,
    },
    "publi24.ro": {
        "strategy": "JS_IF_SHELL",     # încearcă requests, apoi JS dacă pare shell/challenge
        "timeout_s": 20,
        "min_len": 15_000,
        "must_contain": "/anunt/",
        "fail_threshold": 2,
    },
    "default": {
        "strategy": "REQUESTS_ONLY",
        "timeout_s": 15,
        "min_len": 10_000,
        "must_contain": None,
        "fail_threshold": 3,
    },
}