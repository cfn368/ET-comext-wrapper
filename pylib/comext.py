"""
ComextApi — a helper class for exploring and querying the Eurostat Comext
SDMX 2.1 API (dataset DS-045409: EU trade by HS2/4/6 and CN8).

Usage
-----
    from pylib.comext import ComextApi

    api = ComextApi()
    api.info()                          # dataset overview + dimension list
    api.codes("reporter")               # all valid reporter codes
    api.codes("product", search="wind") # search CN codes by label
    api.codes("indicators")             # available value indicators

    df = api.get_data(
        reporter   = "DE+FR+DK",
        partner    = "EXT_EU27_2020",   # extra-EU aggregate
        product    = "85024000+85017100",
        flow       = "1+2",             # 1=import, 2=export
        indicators = "VALUE_IN_EUROS",
        start_period = "2020-01",
    )
"""

import gzip
import json
import re
import time

import pandas as pd
import requests

_BASE = "https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1"


class ComextApi:
    """Interact with the Eurostat Comext SDMX 2.1 API."""

    # DSD version for DS-045409 (update if Eurostat releases a new one)
    _DSD_VERSION = "6.1"

    # Maps dimension id → (codelist id, codelist version)
    _DIM_CODELISTS = {
        "freq":       ("CXT_FREQ",       "1.0"),
        "reporter":   ("CXT_FREE_ISO",   "10.0"),
        "partner":    ("CXT_FREE_ISO",   "10.0"),
        "product":    ("CXT_NC",         "11.0"),
        "flow":       ("CXT_EU_FLUX",    "1.0"),
        "indicators": ("CXT_INDICATORS", "25.0"),
    }

    # Positional dimension order in the SDMX key
    _DIM_ORDER = ["freq", "reporter", "partner", "product", "flow", "indicators"]

    def __init__(self, dataset_id: str = "DS-045409"):
        self.dataset_id = dataset_id
        self._cl_cache: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Public exploration methods
    # ------------------------------------------------------------------

    def info(self) -> None:
        """Print a summary of the dataset and its dimensions."""
        r = requests.get(
            f"{_BASE}/dataflow/ESTAT/{self.dataset_id}", timeout=30
        )
        r.raise_for_status()

        name_en = re.search(r'<c:Name xml:lang="en">([^<]+)</c:Name>', r.text)
        updated = re.search(
            r'<c:AnnotationTitle>([\d\-T:+]+)</c:AnnotationTitle>', r.text
        )

        print(f"Dataset : {self.dataset_id}")
        print(f"Name    : {name_en.group(1) if name_en else '–'}")
        print(f"Updated : {updated.group(1) if updated else '–'}")
        print()

        rows = []
        for dim in self._DIM_ORDER:
            cl_id, cl_ver = self._DIM_CODELISTS[dim]
            cl = self._get_codelist(cl_id, cl_ver)
            first = cl.iloc[0] if len(cl) else ("", "")
            last  = cl.iloc[-1] if len(cl) else ("", "")
            rows.append({
                "dimension":   dim,
                "# codes":     len(cl),
                "first code":  first["id"],
                "first label": first["label"][:40],
                "last code":   last["id"],
                "last label":  last["label"][:40],
            })

        print(pd.DataFrame(rows).to_string(index=False))
        print()
        print("Key order: freq.reporter.partner.product.flow.indicators")

    def codes(
        self,
        dimension: str,
        search: str | None = None,
        aggregates_only: bool = False,
    ) -> pd.DataFrame:
        """
        Return a DataFrame of valid codes and labels for a dimension.

        Parameters
        ----------
        dimension : one of freq / reporter / partner / product / flow / indicators
        search    : optional substring to filter labels (case-insensitive)
        aggregates_only : if True, return only non-ISO-2-letter codes
                          (useful for reporter/partner aggregate groups)
        """
        dim = dimension.lower()
        if dim not in self._DIM_CODELISTS:
            raise ValueError(
                f"Unknown dimension '{dimension}'. "
                f"Choose from: {list(self._DIM_CODELISTS)}"
            )
        cl_id, cl_ver = self._DIM_CODELISTS[dim]
        df = self._get_codelist(cl_id, cl_ver).copy()

        if aggregates_only:
            df = df[df["id"].str.len() != 2]

        if search:
            mask = (
                df["label"].str.contains(search, case=False, na=False)
                | df["id"].str.contains(search, case=False, na=False)
            )
            df = df[mask]

        return df.reset_index(drop=True)

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------

    def get_data(
        self,
        reporter:     str = "DE",
        partner:      str = "EXT_EU27_2020",
        product:      str = "85024000",
        flow:         str = "1+2",
        indicators:   str = "VALUE_IN_EUROS",
        freq:         str = "M",
        start_period: str = "2020-01",
        end_period:   str | None = None,
    ) -> pd.DataFrame:
        """
        Fetch trade data and return a tidy pandas DataFrame.

        Use '+' to combine multiple values per dimension, e.g.
            reporter = "DE+FR+DK"
            product  = "85024000+85017100+85018000"

        Parameters
        ----------
        reporter     : ISO-2 country code(s) or aggregate (e.g. 'EU')
        partner      : partner aggregate — use api.codes('partner', aggregates_only=True)
        product      : 8-digit CN product code(s)
        flow         : 1=import, 2=export, 3=re-export  (default '1+2')
        indicators   : value column  (default 'VALUE_IN_EUROS')
        freq         : M=monthly, Q=quarterly, A=annual
        start_period : e.g. '2020-01'
        end_period   : e.g. '2024-12'  (optional)
        """
        key = f"{freq}.{reporter}.{partner}.{product}.{flow}.{indicators}"
        url = f"{_BASE}/data/{self.dataset_id}/{key}"
        params: dict = {"format": "JSON", "startPeriod": start_period, "compressed": "true"}
        if end_period:
            params["endPeriod"] = end_period

        r = requests.get(url, params=params, timeout=300)
        r.raise_for_status()

        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8"))

        return self._jsonstat_to_df(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_codelist(self, cl_id: str, cl_ver: str) -> pd.DataFrame:
        """Fetch and cache a codelist, returning a DataFrame of id/label."""
        cache_key = f"{cl_id}/{cl_ver}"
        if cache_key in self._cl_cache:
            return self._cl_cache[cache_key]

        r = requests.get(
            f"{_BASE}/codelist/ESTAT/{cl_id}/{cl_ver}", timeout=60
        )
        r.raise_for_status()

        # Parse id + English label pairs from XML
        entries = re.findall(
            r'<s:Code id="([^"]+)"[^>]*>.*?<c:Name xml:lang="en">([^<]+)</c:Name>',
            r.text,
            re.DOTALL,
        )
        df = pd.DataFrame(entries, columns=["id", "label"])

        self._cl_cache[cache_key] = df
        return df

    @staticmethod
    def _jsonstat_to_df(data: dict) -> pd.DataFrame:
        """Convert a JSON-stat response to a flat DataFrame."""
        ids   = data["id"]
        dims  = data["dimension"]
        vals  = data["value"]

        # Build ordered code list per dimension
        levels = []
        for dim in ids:
            cat = dims[dim]["category"]
            idx = cat["index"]
            if isinstance(idx, dict):
                codes = [k for k, _ in sorted(idx.items(), key=lambda kv: kv[1])]
            else:
                codes = list(idx)
            levels.append(codes)

        # Multi-index of all combinations
        mi = pd.MultiIndex.from_product(levels, names=ids)

        # Values (JSON-stat can be sparse dict or dense list)
        if isinstance(vals, dict):
            y = [float("nan")] * mi.size
            for k, v in vals.items():
                y[int(k)] = v
        else:
            y = vals

        df = mi.to_frame(index=False)
        df["value"] = y

        # Drop all-NaN rows (sparse datasets)
        df = df.dropna(subset=["value"]).reset_index(drop=True)

        return df