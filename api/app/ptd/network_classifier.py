"""C2: classify each C1 row's network type and filter to PPO.

Pure functions, built on C1's output (index_parser.build_c1_table /
filter_california). Plan names carry the network type as a token; there is
no dedicated field for it.
"""

from __future__ import annotations

import re
from typing import Any

_NETWORK_TOKENS = ("PPO", "HMO", "EPO", "POS")
_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")


def _tokens(plan_name: str) -> list[str]:
    return _TOKEN_SPLIT_RE.split(plan_name.upper())


def classify_network_type(plan_name: str) -> tuple[str, str]:
    """Return (network_type, basis).

    network_type: PPO / HMO / EPO / POS / "HMO(EOA)" / UNKNOWN.
    basis: how confident the classification is, for the review_required flag.
    """
    tokens = _tokens(plan_name)

    if "EOA" in tokens:
        # Health Net "Elect Open Access": an HMO product that also allows
        # PPO-network access without referral -- officially HMO, not PPO.
        # https://providerlibrary.healthnetcalifornia.com/content/dam/centene/healthnet/pdfs/broker/ca/large/eoa_products.pdf
        return "HMO(EOA)", "eoa_token"

    hits = [t for t in tokens if t in _NETWORK_TOKENS]
    if hits:
        if len(set(hits)) > 1:
            # e.g. "... PPO ... EPO ..." -- take the first-occurring token as
            # the base network, flag for human review.
            return hits[0], "multi_token_flagged"
        return hits[0], "token_match"

    # Concatenated token, e.g. "CUSPPO" (no separator before PPO).
    for token in tokens:
        for net in _NETWORK_TOKENS:
            if token != net and token.endswith(net):
                return net, "suffix_match"

    return "UNKNOWN", "no_token"


def classify_table(table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """C1 rows -> C1 rows + network_type / network_type_basis / review_required."""
    classified = []
    for row in table:
        network_type, basis = classify_network_type(row["plan_name"])
        classified.append(
            {
                **row,
                "network_type": network_type,
                "network_type_basis": basis,
                "review_required": basis != "token_match",
            }
        )
    return classified


def filter_ppo(table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in classify_table(table) if row["network_type"] == "PPO"]
