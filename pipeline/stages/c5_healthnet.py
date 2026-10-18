"""C5-HN: verify C5 NPI addresses against Health Net's public provider directory (PCES API).

Input:  data/stage/c5/c5_address_candidates.csv (NPI -> candidate addresses)
        NPPES monthly file inside the dataset archive (NPI -> name, type, license)
Output: data/stage/c5_healthnet/healthnet_evidence.csv   one row per (NPI, Health Net location)
        data/stage/c5_healthnet/healthnet_npi_status.csv one row per NPI with rule-coded status
        data/stage/c5_healthnet/_manifest.json

Rules:
  R-C5-HN-01  Search by NPPES name (org legal name for Type 2, "First M Last" for Type 1).
              Accept a directory record only when its NPI list contains the C5 NPI exactly.
  R-C5-HN-02  A location counts only if CA, a network cycle is active on the run date,
              and excludeFromDirectory != "Y".
  R-C5-HN-03  Target network = product networkId in HN_TARGET_NETWORK_IDS (default 8201,
              "HealthNet Commercial PPO" / carrier "CA PPO Large and Small", observed 2026-10-18).
  R-C5-HN-04  Type 2 NPI not listed itself, and its legal name is a person + corp suffix
              ("SANG H BAIK M.D., INC"): search the person; accept an individual record only
              when one of its active target-PPO addresses equals the org's C5/NPPES address.
              Name alone never links two NPIs.
  R-C5-HN-05  Directory absence is NOT evidence of non-participation (Health Net excludes some
              facility/non-public providers from the directory).
  R-C5-HN-06  Target-network location whose cycle is date-current but excludeFromDirectory=Y
              (reasons seen: Claims History, Provider Request, Location Limit) = contracted but hidden.
  R-C5-HN-07  Search-name chain (stop at first exact-NPI hit): NPPES legal name, legal name without
              LLC/INC/"A MEDICAL CORPORATION", NPPES DBA name, rate-file TIN business name; individuals
              "First M Last" then "First Last". NPIs with no NPPES name (deactivated / missing) use the
              rate-file business name. A name that errors even at page size 10 is skipped, not fatal.
              Reported as PAYER_PPO_HIDDEN_*; weaker than a displayed listing ("Claims History" means
              no recent claims there), so it never outranks R-C5-HN-01.

The API key is the public key shipped in the Health Net Find-a-Provider web bundle. It is read at
runtime from a saved copy of that bundle (PTD_HN_APP_JS) and is never written to disk or logs.

Reproducible without the API: the raw responses of the 2026-10-18 run are in the dataset archive
(healthnet/healthnet_pces_responses_2026-10-18.zip); `--offline` / `python -m pipeline c5hn` replays them.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pipeline.config import Config
from pipeline.io.archive import open_source_zip
from pipeline.io.manifest import write_manifest
from pipeline.stages.c5_address import _normalize_address, _same_building, _text, c4_candidate_keys

NPPES_MEMBER = "nppes/NPPES_Data_Dissemination_October_2026_V2.zip"
# R-C5-HN-03: CA commercial-group PPO only. Seen in 3,999 cached responses (2026-10-18):
#   8201 HealthNet Commercial PPO  (carrier "CA PPO Large and Small", plan Commercial)
#   8203 HealthNet Commercial PS3  (carrier "CA Small Group EnhancedCare PPO", plan Commercial)
# Excluded on purpose: Ambetter PPO 13295/5236/4679 (individual exchange), 10036 Reciprocity
# (Medicare Advantage), OR/WCG/WellCare Medicare PPOs, DBP dental PPOs 14839/14118/6117.
DEFAULT_TARGET_NETWORK_IDS = ("8201", "8203")
HN_ARCHIVE_MEMBER = "healthnet/healthnet_pces_responses_2026-10-18.zip"  # raw responses, inside the dataset
HN_SNAPSHOT_DATE = "2026-10-18"  # date those responses were fetched; offline runs evaluate "current" as of it
PAGE_SIZE = 100

CORP_SUFFIX = re.compile(
    r"\b(A\s+)?(PROFESSIONAL|MEDICAL|DENTAL|OPTOMETRIC|PSYCHOLOGICAL|NURSING|CHIROPRACTIC)?\s*"
    r"(CORPORATION|CORP|INC|INCORPORATED|APC|APMC|PC|LLC|PLLC|LTD|MD|M D|DO|D O|DDS|DMD|DPM|OD|PHD|PSYD|"
    r"FACS|FACP|MPH|LCSW|LMFT|NP|PA|RN|DC)\b"
)
ORG_WORDS = re.compile(
    r"\b(CENTER|CENTRE|GROUP|ASSOCIATES|CLINIC|HOSPITAL|HEALTH|HEALTHCARE|MEDICINE|SERVICES|PARTNERS|"
    r"INSTITUTE|NETWORK|SYSTEM|SURGERY|SURGICAL|LAB|LABORATORY|IMAGING|RADIOLOGY|PHARMACY|THERAPY|"
    r"FOUNDATION|UNIVERSITY|COUNTY|CARE|FAMILY|PEDIATRIC|WOMENS|DIALYSIS|AMBULATORY)\b"
)


# ---------- pure helpers (unit-tested) ----------

def query_name(text: str) -> str:
    """Directory name match is token based; drop punctuation so 'M.D., INC' does not block it."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9' ]", " ", text or "")).strip()


def person_name(first: str, middle: str, last: str) -> str:
    mid = _text(middle)[:1]
    return query_name(" ".join(x for x in (_text(first), mid, _text(last)) if x))


def person_from_org(org_name: str) -> str:
    """'SANG H BAIK M.D., INC' -> 'SANG H BAIK'; '' when the name looks like a real organization."""
    name = query_name(org_name).upper()
    if not name or ORG_WORDS.search(name):
        return ""
    stripped = re.sub(r"\s+", " ", CORP_SUFFIX.sub(" ", name)).strip()
    if stripped == name:  # no corp/credential suffix -> not a person-corp pattern
        return ""
    return stripped if 2 <= len(stripped.split()) <= 4 else ""


def strip_corp(name: str) -> str:
    """'NEWPORT SURGICAL PARTNERS LLC' -> 'NEWPORT SURGICAL PARTNERS' (100% token match fails on LLC/INC)."""
    s = re.sub(r"\s+", " ", CORP_SUFFIX.sub(" ", query_name(name).upper())).strip()
    s = re.sub(r"^(THE|A)\s+|\s+(A|THE|OF)$", "", s).strip()
    return s if len(s) >= 3 else ""


def candidate_names(info: dict[str, Any], tin_names: Iterable[str] = ()) -> list[str]:
    """R-C5-HN-07 search-name chain, most specific first. Every hit still needs the exact NPI."""
    etype = info.get("Entity_Type", "")
    if etype == "1":
        f, m, last = info.get("First_Name", ""), info.get("Middle_Name", ""), info.get("Last_Name", "")
        names = [person_name(f, m, last), person_name(f, "", last)]
    else:  # Type 2, or NPI missing/deactivated in NPPES: org names, then the rate file's TIN business name
        orgs = [info.get("Org_Name", ""), info.get("Other_Org_Name", ""), *tin_names]
        names = [n for o in orgs for n in (query_name(o), strip_corp(o))]
    return [n for n in dict.fromkeys(x.upper() for x in names) if len(n) >= 3]


def name_query(name: str, offset: int = 0, size: int = PAGE_SIZE,
               network_ids: Iterable[str] = DEFAULT_TARGET_NETWORK_IDS) -> dict[str, Any]:
    """Query shape observed from the Find-a-Provider web app (2026-10-18).
    Filtering to the target PPO networks server-side keeps responses small (fixes most 413s) and
    returns no Ambetter/HMO/Medicare records at all."""
    def match(field: str) -> dict[str, Any]:
        return {"nameMatch": {"field": field, "value": name, "minimumMatch": "100%"}}

    criteria = [
        match("locations.search_root_pracFullName"),
        match("locations.search_root_pracFullAlternateName"),
        match("locations.search_root_providerName"),
        {"requireAll": {"criteria": [
            match("locations.name"),
            {"value": {"field": "locations.search_root_entityType", "value": "prov"}},
        ]}},
    ]
    nested = {"nested": {"path": "locations", "score_mode": "max",
                         "query": {"requireAny": {"criteria": criteria}}}}
    ids = [str(x) for x in network_ids]
    q: dict[str, Any] = {"size": size, "customQuery": {"requireAll": {"criteria": [
        nested, {"values": {"field": "network.product.networkId", "values": ids}}]}} if ids else nested}
    if offset:
        q["from"] = offset
    return q


def _cycle_dated(c: dict[str, Any], asof: str) -> bool:
    start, end = _text(c.get("startDate"))[:10], _text(c.get("endDate"))[:10]
    return (not start or start <= asof) and (not end or end >= asof)


def _displayed(loc: dict[str, Any], asof: str) -> bool:
    """Same test the public web app applies before showing a location."""
    return any(_text(x.get("eligibleIndicator")).upper() == "Y" and _cycle_dated(x, asof)
               for x in loc.get("eligibleForDisplay") or [])


EVIDENCE_FIELDS = [
    "HN_Entity_ID", "HN_Entity_Type", "HN_NPIs", "HN_Location_Name", "HN_Address", "HN_Normalized_Address",
    "HN_Phone", "HN_Product_Network_ID", "HN_Product", "HN_Carrier", "HN_Health_Plan", "HN_Target_Network",
    "HN_Active", "HN_Contract_Current", "HN_Exclusion_Reason", "HN_Last_Verified", "HN_Verified_Source", "HN_Record_Updated",
]


def extract_locations(response: dict[str, Any], asof: str, target_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Flatten a PCES response into one row per (entity, CA location)."""
    target = {str(x) for x in target_ids}
    rows = []
    for hit in response.get("results", []):
        src = hit.get("source", hit)
        e = src.get("carrierEntity", src)
        net = e.get("network", {}) or {}
        prod = net.get("product", {}) or {}
        npis = [_text(x.get("number")) for x in e.get("nationalProviderIdentifiers", []) or [] if x.get("number")]
        for loc in e.get("locations", []) or []:
            a = loc.get("address", {}) or {}
            if _text(a.get("stateCode")).upper() != "CA":
                continue
            cycles = loc.get("networkLocationCycles", []) or []
            verified = {}
            for at in loc.get("attributes", []) or []:
                if at.get("name") == "Prac Loc Last Verified Date":
                    for f in at.get("fields", []) or []:
                        verified[_text(f.get("name"))] = _text(f.get("value_date", f.get("value")))
            phone = loc.get("pracPhones") or loc.get("phone") or {}
            if isinstance(phone, list):
                phone = phone[0] if phone else {}
            rows.append({
                "HN_Entity_ID": _text(e.get("entityId")),
                "HN_Entity_Type": _text(e.get("entityType")),
                "HN_NPIs": "|".join(npis),
                "HN_Location_Name": _text(loc.get("name")),
                "HN_Address": ", ".join(_text(x) for x in (a.get("addressLine1"), a.get("addressLine2"),
                                                          a.get("city"), a.get("stateCode"), a.get("zipCode"))
                                        if _text(x)),
                "HN_Normalized_Address": _normalize_address(a.get("addressLine1"), a.get("addressLine2"),
                                                            a.get("city"), a.get("stateCode"), a.get("zipCode")),
                "HN_Phone": _text(phone.get("phone") if isinstance(phone, dict) else phone),
                "HN_Product_Network_ID": _text(prod.get("networkId")),
                "HN_Product": _text(prod.get("name")),
                "HN_Carrier": _text((net.get("carrier") or {}).get("name")),
                "HN_Health_Plan": _text((net.get("healthPlan") or {}).get("name")),
                "HN_Target_Network": "yes" if _text(prod.get("networkId")) in target else "no",
                # R-C5-HN-02: "shown" = the Find-a-Provider web app's own location filter
                # (eligibleForDisplay.eligibleIndicator == "Y" and start <= today <= end, read from its
                # bundle 2026-10-18), not excludeFromDirectory: the two disagree on ~5.9k CA locations.
                "HN_Active": "yes" if _displayed(loc, asof) and any(_cycle_dated(c, asof) for c in cycles) else "no",
                # R-C5-HN-06: date-current cycle that Health Net hides from the public directory
                "HN_Contract_Current": "yes" if any(_cycle_dated(c, asof) for c in cycles) else "no",
                "HN_Exclusion_Reason": "|".join(sorted({_text(c.get("exclusionReason")) for c in cycles
                                                        if _cycle_dated(c, asof)
                                                        and _text(c.get("excludeFromDirectory")).upper() == "Y"
                                                        and _text(c.get("exclusionReason"))})),
                "HN_Last_Verified": verified.get("Verified Date", ""),
                "HN_Verified_Source": verified.get("Source", ""),
                "HN_Record_Updated": _text(e.get("updateTime")),
            })
    return rows


same_address = _same_building  # R-C5-HN-01 match = C5's building-level rule (R-C5-11)


def classify(rows: list[dict[str, Any]], c5_addrs: list[str]) -> tuple[str, str, str]:
    """Return (status, rule, matched HN address) for rows already filtered to one NPI."""
    if not rows:
        return "NOT_FOUND_IN_PAYER_DIRECTORY", "R-C5-HN-05", ""
    target = [r for r in rows if r["HN_Target_Network"] == "yes"]
    good = [r for r in target if r["HN_Active"] == "yes"]
    hidden = [r for r in target if r["HN_Active"] == "no" and r["HN_Contract_Current"] == "yes"]
    for pool, prefix, rule in ((good, "PAYER_PPO", "R-C5-HN-01"), (hidden, "PAYER_PPO_HIDDEN", "R-C5-HN-06")):
        if not pool:
            continue
        for r in pool:
            if any(same_address(r["HN_Normalized_Address"], c) for c in c5_addrs):
                return f"{prefix}_ADDRESS_MATCH", rule, r["HN_Address"]
        return f"{prefix}_ADDRESS_NEW", rule, pool[0]["HN_Address"]
    return "LISTED_NON_TARGET_OR_INACTIVE_ONLY", "R-C5-HN-03", ""


# ---------- IO ----------

@dataclass
class Client:
    url: str
    headers: dict[str, str]
    cache_dir: Path
    min_interval: float
    _next: float = 0.0
    calls: int = 0
    cache_hits: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # raw responses shipped in the dataset archive (healthnet/healthnet_pces_responses_*.zip)
    archived: zipfile.ZipFile | None = None
    offline: bool = False  # never call the API; cache/archive only

    @classmethod
    def offline_client(cls, cache_dir: Path, archived: zipfile.ZipFile | None) -> Client:
        return cls("offline", {}, cache_dir, 0.0, archived=archived, offline=True)

    def _throttle(self) -> None:
        """Global rate limit shared by all worker threads: reserve the next send slot."""
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self.min_interval
            self.calls += 1
        if slot > now:
            time.sleep(slot - now)

    @classmethod
    def from_app_js(cls, app_js: Path, cache_dir: Path, rps: float) -> Client:
        s = app_js.read_text(encoding="utf-8")
        m = re.search(r"\d+:function\(e\)\{e\.exports=JSON\.parse\('(\[\{\"env\".*?)'\)\}", s)
        if not m:
            raise RuntimeError(f"Health Net config not found in {app_js}; re-save the Find-a-Provider bundle")
        cfg = json.loads(bytes(m.group(1), "utf-8").decode("unicode_escape"))
        p = next(x for x in cfg if x.get("env") == "prod")["apiAccessConfiguration"]["pcesAPI"]
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cls(p["apiGatewayURL"] + p["policyName"] + "/query",
                   {"Content-Type": "application/json; charset=utf-8", "x-api-key": p["basicAuthKey"]},
                   cache_dir, 1.0 / rps)

    def post(self, body: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(body, sort_keys=True)
        # gzip: raw responses average ~650 KB (up to 10 MB); plain JSON filled 2 GB in 4 minutes
        path = self.cache_dir / (hashlib.sha256(raw.encode()).hexdigest()[:24] + ".json.gz")
        if path.exists():
            with self._lock:
                self.cache_hits += 1
            return json.loads(gzip.decompress(path.read_bytes()))["response"]
        if self.archived is not None:
            with self._lock:  # nested ZipFile shares one stream: not safe for concurrent reads
                try:
                    blob = self.archived.read(path.name)
                except KeyError:
                    blob = None
                else:
                    self.cache_hits += 1
            if blob is not None:
                return json.loads(gzip.decompress(blob))["response"]
        if self.offline:
            # Uncached = the live call failed (413/400 are never cached). Replay it as that failure so
            # search() takes the same shrink-page / next-name path the live run took.
            raise urllib.error.HTTPError(self.url, 413, "not in cache/archive (offline)", {}, io.BytesIO(b""))
        data: dict[str, Any] = {}
        for attempt in range(4):
            self._throttle()
            try:
                req = urllib.request.Request(self.url, data=raw.encode(), headers=self.headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.load(resp)
                break
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise RuntimeError(f"PCES HTTP {e.code}: key rotated? re-save the web bundle") from e
                if e.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise
            time.sleep(2 ** (attempt + 1))
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")  # atomic: no half-written cache under threads
        tmp.write_bytes(gzip.compress(json.dumps({"retrieved_at": datetime.now(UTC).isoformat(),
                                   "request": body, "response": data}).encode(), compresslevel=6))
        tmp.replace(path)
        return data

    def search(self, name: str, network_ids: Iterable[str] = DEFAULT_TARGET_NETWORK_IDS
               ) -> tuple[list[dict[str, Any]], int, bool]:
        """All pages for one name. Returns (responses, totalHits, truncated)."""
        out, offset, total, size = [], 0, 0, PAGE_SIZE
        while True:  # every page until the API reports no more hits
            try:
                d = self.post(name_query(name, offset, size, network_ids))
            except urllib.error.HTTPError as e:
                # 413 = response over gateway size limit (big orgs: Apria, LabCorp); 400 seen on the same
                # class of broad names. Shrink the page and retry the same offset.
                if e.code in (400, 413) and size > 10:
                    size = max(10, size // 4)
                    continue
                raise
            out.append(d)
            total = int(d.get("totalHits") or 0)
            got = len(d.get("results", []))
            offset += got
            if got < size or offset >= total:
                return out, total, False


def build_lookup_input(archive: Path, npis: set[str]) -> dict[str, dict[str, str]]:
    """Stream NPPES (nested zip in the dataset archive) for name/type/license/address of C5 NPIs."""
    csv.field_size_limit(10**9)
    found: dict[str, dict[str, str]] = {}
    with zipfile.ZipFile(archive) as outer:
        member = next(n for n in outer.namelist() if n.endswith(NPPES_MEMBER))
        with outer.open(member) as nested, zipfile.ZipFile(nested) as z:
            inner = next(n for n in z.namelist()
                         if n.split("/")[-1].startswith("npidata_pfile_") and "fileheader" not in n)
            with z.open(inner) as raw:
                for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline="")):
                    if row["NPI"] not in npis:
                        continue
                    g = row.get
                    found[row["NPI"]] = {
                        "Entity_Type": g("Entity Type Code", ""),
                        "Org_Name": g("Provider Organization Name (Legal Business Name)", ""),
                        "Other_Org_Name": g("Provider Other Organization Name", ""),  # DBA name
                        "First_Name": g("Provider First Name", ""),
                        "Middle_Name": g("Provider Middle Name", ""),
                        "Last_Name": g("Provider Last Name (Legal Name)", ""),
                        "License": g("Provider License Number_1", ""),
                        "NPPES_Normalized_Address": _normalize_address(
                            g("Provider First Line Business Practice Location Address"),
                            g("Provider Second Line Business Practice Location Address"),
                            g("Provider Business Practice Location Address City Name"),
                            g("Provider Business Practice Location Address State Name"),
                            g("Provider Business Practice Location Address Postal Code")),
                    }
                    if len(found) == len(npis):
                        break
    return found


def lookup_npi(client: Client, npi: str, info: dict[str, str], c5_addrs: list[str], asof: str,
               target_ids: tuple[str, ...], tin_names: tuple[str, ...] = ()
               ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One NPI end to end (R-C5-HN-01..07). Thread-safe: only touches the shared rate-limited client."""
    etype = info.get("Entity_Type", "")
    names = candidate_names(info, tin_names)
    addrs = [a for a in c5_addrs + [info.get("NPPES_Normalized_Address", "")] if a]
    method, dir_npi, total, trunc, mine, used, tried, errors = "EXACT_NPI", npi, 0, False, [], "", [], []

    def run(name: str) -> list[dict[str, Any]]:
        nonlocal total, trunc
        tried.append(name)
        try:
            pages, total, trunc = client.search(name, target_ids)
        except urllib.error.HTTPError as e:  # still too big at size 10, or rejected: try the next name
            if e.code not in (400, 413):
                raise
            errors.append(f"{name}: HTTP {e.code}")
            return []
        return [r for d in pages for r in extract_locations(d, asof, target_ids)]

    for name in names:  # R-C5-HN-07: stop at the first name that returns this exact NPI
        mine = [r for r in run(name) if npi in r["HN_NPIs"].split("|")]
        if mine:
            used = name
            break
    person = person_from_org(info.get("Org_Name", "")) if etype == "2" and not mine else ""
    toks = person.split()
    for p in dict.fromkeys([person, f"{toks[0]} {toks[-1]}" if len(toks) > 2 else ""]):  # R-C5-HN-04
        if not p:
            continue
        cand = [r for r in run(p)
                if r["HN_Entity_Type"] == "prac" and r["HN_Active"] == "yes"
                and any(same_address(r["HN_Normalized_Address"], a) for a in addrs)]
        if cand:
            mine, method, dir_npi, used = cand, "PERSON_CORP_NAME_ADDRESS_CROSSWALK", cand[0]["HN_NPIs"], p
            break
    if not names:
        status, rule, matched = "NO_SEARCH_NAME", "R-C5-HN-07", ""
    elif not mine and errors and len(errors) == len(tried):
        status, rule, matched = "ERROR", "", "; ".join(errors)[:300]
    else:
        status, rule, matched = classify(mine, addrs)
    if method != "EXACT_NPI" and status == "PAYER_PPO_ADDRESS_MATCH":
        status, rule = "CROSSWALK_PPO_ADDRESS_MATCH", "R-C5-HN-04"
    evidence = [{"NPI": npi, "Search_Name": used, "Match_Method": method,
                 "Directory_NPI": dir_npi, **r} for r in mine]
    row = {"NPI": npi, "Entity_Type": etype, "Search_Name": used or (names[0] if names else ""),
           "Names_Tried": " || ".join(tried), "HN_Status": status,
           "HN_Rule": rule, "HN_Match_Method": method if mine else "",
           "HN_Directory_NPI": dir_npi if mine else "", "HN_Matched_Address": matched,
           "HN_Total_Hits": total, "HN_Truncated": "yes" if trunc else "no",
           "C5_Addresses": " | ".join(dict.fromkeys(addrs))}
    return evidence, row


def _safe_lookup(*args: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """A single failed NPI is recorded as ERROR instead of killing a long run; rerun retries it."""
    try:
        return lookup_npi(*args)
    except RuntimeError:
        raise  # auth failure (key rotated): stop everything
    except Exception as e:  # noqa: BLE001
        detail = f"{type(e).__name__}: {e}"
        if isinstance(e, urllib.error.HTTPError):
            try:
                detail += " | " + e.read()[:200].decode(errors="replace")
            except Exception:  # noqa: BLE001, S110
                pass
        return [], {"NPI": args[1], "Entity_Type": args[2].get("Entity_Type", ""), "HN_Status": "ERROR",
                    "HN_Rule": "", "HN_Matched_Address": detail[:300]}


def _log_npi(i: int, n: int, row: dict[str, Any], evidence: list[dict[str, Any]]) -> None:
    """One detailed line per NPI, plus each matching Health Net location under it."""
    print(f"[{i}/{n}] {row['NPI']} type={row.get('Entity_Type') or '?'} name=\"{row.get('Search_Name', '')}\" "
          f"hits={row.get('HN_Total_Hits', 0)}{' TRUNCATED' if row.get('HN_Truncated') == 'yes' else ''} "
          f"-> {row['HN_Status']} {row.get('HN_Rule', '')}", flush=True)
    if row["HN_Status"] == "ERROR":
        print(f"      error: {row.get('HN_Matched_Address', '')}", flush=True)
    for r in evidence:
        flags = ("PPO" if r["HN_Target_Network"] == "yes" else "other-net") + \
                (" active" if r["HN_Active"] == "yes" else " inactive")
        print(f"      {r['Match_Method']} dirNPI={r['Directory_NPI']} [{flags}] net={r['HN_Product_Network_ID']} "
              f"\"{r['HN_Product']}\" | {r['HN_Address']} | ph={r['HN_Phone'] or '-'} "
              f"| verified={r['HN_Last_Verified'] or '-'} ({r['HN_Verified_Source'] or '-'})", flush=True)
    if row.get("HN_Status", "").startswith(("PAYER_PPO", "CROSSWALK")):
        print(f"      C5: {row.get('C5_Addresses', '')}", flush=True)


def run_c5_healthnet(cfg: Config, *, limit: int | None = None, only_npis: Iterable[str] = (),
                     rps: float = 3.0, workers: int = 8, asof: str | None = None,
                     verbose: bool = True, offline: bool = False) -> dict[str, int]:
    """offline=True rebuilds the evidence from the responses archived in the dataset (no API, no key),
    evaluated as of the snapshot date so a clean clone reproduces the 2026-10-18 result."""
    started = time.monotonic()
    rps, workers = max(rps, 0.1), max(1, workers)
    asof = asof or (HN_SNAPSHOT_DATE if offline else date.today().isoformat())
    out_dir = cfg.stage_dir("c5_healthnet")
    out_dir.mkdir(parents=True, exist_ok=True)
    target_ids = tuple(x for x in os.environ.get("HN_TARGET_NETWORK_IDS",
                                                 ",".join(DEFAULT_TARGET_NETWORK_IDS)).split(",") if x)
    cache_dir = cfg.data_dir / "raw" / "healthnet_pces" / "cache"
    stack = ExitStack()
    archived, archived_src = stack.enter_context(open_source_zip(cfg.archive, HN_ARCHIVE_MEMBER))
    if offline:
        client = Client.offline_client(cache_dir, archived)
    else:
        app_js = Path(os.environ.get("PTD_HN_APP_JS", cfg.data_dir / "raw" / "healthnet_pces" / "app.js"))
        client = Client.from_app_js(app_js, cache_dir, rps)
        client.archived = archived  # archived responses also serve as cache for live runs

    # Input is C4 (runs before C5, which consumes this stage's evidence). Addresses for status/crosswalk
    # come from NPPES; C5 does the final address matching.
    c5_addrs: dict[str, list[str]] = {}
    tin_names: dict[str, list[str]] = {}  # rate-file business name per NPI: fallback search name
    with open(cfg.stage_dir("c4") / "selected_rates.csv", newline="", encoding="utf-8") as f:
        for (npi, _tin), name in c4_candidate_keys(list(csv.DictReader(f))).items():
            c5_addrs.setdefault(npi, [])
            if name and name not in tin_names.setdefault(npi, []):
                tin_names[npi].append(name)
    npis = sorted(set(only_npis) or set(c5_addrs))[: limit or None]

    lookup_path = out_dir / "lookup_input.json"
    lookup = json.loads(lookup_path.read_text()) if lookup_path.exists() else {}
    # entries from before the DBA name was captured are re-read once
    lookup = {k: v for k, v in lookup.items() if "Other_Org_Name" in v or v.get("Entity_Type") == "NOT_IN_NPPES"}
    if not set(npis) <= set(lookup):
        missing = set(npis) - set(lookup)
        lookup.update(build_lookup_input(cfg.archive, missing))
        # remember NPIs absent from NPPES too, else every run re-scans the full 9 GB file for them
        lookup.update({n: {"Entity_Type": "NOT_IN_NPPES"} for n in missing - set(lookup)})
        lookup_path.write_text(json.dumps(lookup))

    ev_cols = ["NPI", "Search_Name", "Match_Method", "Directory_NPI", *EVIDENCE_FIELDS]
    st_cols = ["NPI", "Entity_Type", "Search_Name", "Names_Tried", "HN_Status", "HN_Rule", "HN_Match_Method",
               "HN_Directory_NPI", "HN_Matched_Address", "HN_Total_Hits", "HN_Truncated", "C5_Addresses"]
    counts: dict[str, int] = {}
    with open(out_dir / "healthnet_evidence.csv", "w", newline="") as fe, \
         open(out_dir / "healthnet_npi_status.csv", "w", newline="") as fs:
        ev, st = csv.DictWriter(fe, ev_cols), csv.DictWriter(fs, st_cols)
        ev.writeheader()
        st.writeheader()
        # Threads only overlap network latency; the client's shared limiter caps total request rate.
        # map() yields in input order, so output files stay deterministic across runs.
        print(f"c5hn: {len(npis)} NPIs, workers={workers}, rps={rps}, asof={asof}, "
              f"target_networks={','.join(target_ids)}", flush=True)
        run_t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = pool.map(_safe_lookup, *zip(*[
                (client, npi, lookup.get(npi, {}), c5_addrs.get(npi, []), asof, target_ids,
                 tuple(tin_names.get(npi, []))) for npi in npis]))
            for i, (evidence, row) in enumerate(results, 1):
                ev.writerows(evidence)
                st.writerow(row)
                counts[row["HN_Status"]] = counts.get(row["HN_Status"], 0) + 1
                if verbose:
                    _log_npi(i, len(npis), row, evidence)
                if i % 50 == 0 or i == len(npis):
                    fe.flush()
                    fs.flush()
                    el = time.monotonic() - run_t0
                    eta = el / i * (len(npis) - i)
                    print(f"== progress {i}/{len(npis)} ({i / len(npis):.0%}) elapsed={el / 60:.1f}m "
                          f"eta={eta / 60:.1f}m api_calls={client.calls} cache_hits={client.cache_hits} "
                          f"rate={client.calls / el if el else 0:.2f}/s {counts}", flush=True)
    stack.close()
    counts.update(npis=len(npis), api_calls=client.calls, cache_hits=client.cache_hits)
    write_manifest(out_dir / "_manifest.json", stage="c5_healthnet", config_path=cfg.root / "config.yaml",
                   sources=[{"pces_endpoint": client.url, "asof": asof, "target_network_ids": list(target_ids),
                             "workers": workers, "rps": rps, "offline": offline,
                             "archived_responses": archived_src},
                            {"archive": str(cfg.archive), "member": NPPES_MEMBER}],
                   counts=counts, started_at=started)
    return counts


if __name__ == "__main__":
    import argparse

    from pipeline.config import load_config

    ap = argparse.ArgumentParser(prog="python -m pipeline.stages.c5_healthnet")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--npi", action="append", default=[])
    ap.add_argument("--rps", type=float, default=3.0, help="total requests/s across all workers (default 3; be polite to a live API)")
    ap.add_argument("--workers", type=int, default=8, help="concurrent NPIs in flight")
    ap.add_argument("--quiet", action="store_true", help="only progress lines, no per-NPI detail")
    ap.add_argument("--offline", action="store_true",
                    help="rebuild from the responses archived in the dataset; no API calls, no key needed")
    a = ap.parse_args()
    counts = run_c5_healthnet(load_config(), limit=a.limit, only_npis=a.npi, rps=a.rps, workers=a.workers,
                              verbose=not a.quiet, offline=a.offline)
    print("\n== summary")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:40s} {v}")
