"""
ComextApi  — Eurostat Comext SDMX 2.1 API (DS-045409: EU goods trade by CN8).
ServicesApi — Eurostat SDMX 2.1 API (BOP_ITS6_DET: EU international trade in services).

Usage
-----
    from comext_wrapper import ComextApi, ServicesApi

    # Goods
    api = ComextApi()
    api.info()
    api.codes("product", search="heat pump")
    df = api.get_data(
        reporter     = "DE+FR+DK",
        partner      = "EXT_EU27_2020",
        product      = "85024000+85017100",
        flow         = "1+2",
        indicators   = "VALUE_IN_EUROS",
        start_period = "2020-01",
    )

    # Services
    api = ServicesApi()
    api.info()
    api.codes("bop_item", search="transport")
    df = api.get_data(
        geo          = "DK+DE+FR",
        partner      = "WRL_REST",
        bop_item     = "S",
        stk_flow     = "CRE+DEB",
        currency     = "MIO_EUR",
        start_period = "2015",
    )
"""

import gzip
import json
import re

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

__version__ = "0.2.0"
__all__ = ["ComextApi", "ServicesApi"]

_COMEXT_BASE = "https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1"
_ESTAT_BASE  = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1"

_retry   = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503])
_adapter = HTTPAdapter(max_retries=_retry)
_session = requests.Session()
_session.mount("https://", _adapter)


class _SdmxApi:
    """Shared SDMX 2.1 machinery. Subclass and set _BASE, _DSD_VERSION, _DIM_CODELISTS, _DIM_ORDER."""

    _BASE: str
    _DSD_VERSION: str
    _DIM_CODELISTS: dict[str, tuple[str, str]]
    _DIM_ORDER: list[str]

    _cl_cache: dict[str, pd.DataFrame] = {}

    def __init__(self, dataset_id: str):
        self.dataset_id = dataset_id

    # ------------------------------------------------------------------
    # Public exploration methods
    # ------------------------------------------------------------------

    def info(self) -> pd.DataFrame:
        """Print a summary of the dataset and return a dimensions DataFrame."""
        r = _session.get(
            f"{self._BASE}/dataflow/ESTAT/{self.dataset_id}", timeout=30
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

        summary = pd.DataFrame(rows)
        print(summary.to_string(index=False))
        print()
        print(f"Key order: {'.'.join(self._DIM_ORDER)}")

        return summary

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
        dimension       : one of the dataset's dimensions (see _DIM_ORDER)
        search          : optional substring to filter labels (case-insensitive)
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_codelist(self, cl_id: str, cl_ver: str) -> pd.DataFrame:
        """Fetch and cache a codelist, returning a DataFrame of id/label."""
        cache_key = f"{cl_id}/{cl_ver}"
        if cache_key in self._cl_cache:
            return self._cl_cache[cache_key]

        r = _session.get(
            f"{self._BASE}/codelist/ESTAT/{cl_id}/{cl_ver}", timeout=60
        )
        if r.status_code == 404:
            raise RuntimeError(
                f"Codelist {cl_id} version {cl_ver} not found (HTTP 404). "
                f"Eurostat may have released a new version — update _DIM_CODELISTS."
            )
        r.raise_for_status()

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
        ids  = data["id"]
        dims = data["dimension"]
        vals = data["value"]

        levels = []
        for dim in ids:
            cat = dims[dim]["category"]
            idx = cat["index"]
            if isinstance(idx, dict):
                codes = [k for k, _ in sorted(idx.items(), key=lambda kv: kv[1])]
            else:
                codes = list(idx)
            levels.append(codes)

        mi = pd.MultiIndex.from_product(levels, names=ids)

        if isinstance(vals, dict):
            y = [float("nan")] * mi.size
            for k, v in vals.items():
                y[int(k)] = v
        else:
            y = vals

        df = mi.to_frame(index=False)
        df["value"] = y
        df = df.dropna(subset=["value"]).reset_index(drop=True)

        if "time" in df.columns:
            df = df.rename(columns={"time": "period"})

        return df


# ==============================================================================
# Goods trade
# ==============================================================================

class ComextApi(_SdmxApi):
    """Interact with the Eurostat Comext SDMX 2.1 API (goods trade, DS-045409)."""

    _BASE        = _COMEXT_BASE
    _DSD_VERSION = "6.1"

    _DIM_CODELISTS = {
        "freq":       ("CXT_FREQ",       "1.0"),
        "reporter":   ("CXT_FREE_ISO",   "10.0"),
        "partner":    ("CXT_FREE_ISO",   "10.0"),
        "product":    ("CXT_NC",         "11.0"),
        "flow":       ("CXT_EU_FLUX",    "1.0"),
        "indicators": ("CXT_INDICATORS", "25.0"),
    }

    _DIM_ORDER = ["freq", "reporter", "partner", "product", "flow", "indicators"]

    def __init__(self, dataset_id: str = "DS-045409"):
        super().__init__(dataset_id)

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
        Fetch goods trade data and return a tidy pandas DataFrame.

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
        url = f"{self._BASE}/data/{self.dataset_id}/{key}"
        params: dict = {"format": "JSON", "startPeriod": start_period, "compressed": "true"}
        if end_period:
            params["endPeriod"] = end_period

        r = _session.get(url, params=params, timeout=300)
        r.raise_for_status()

        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8"))

        return self._jsonstat_to_df(data)


# ==============================================================================
# Services trade
# ==============================================================================

class ServicesApi(_SdmxApi):
    """Interact with the Eurostat SDMX 2.1 API for international trade in services (BOP_ITS6_DET)."""

    _BASE        = _ESTAT_BASE
    _DSD_VERSION = "44.0"

    _DIM_CODELISTS = {
        "freq":     ("FREQ",     "3.9"),
        "currency": ("CURRENCY", "5.1"),
        "bop_item": ("BOP_ITEM", "7.3"),
        "stk_flow": ("STK_FLOW", "6.2"),
        "partner":  ("PARTNER",  "31.2"),
        "geo":      ("GEO",      "28.0"),
    }

    # Positional order in the SDMX key (from the DSD)
    _DIM_ORDER = ["freq", "currency", "bop_item", "stk_flow", "partner", "geo"]

    def __init__(self, dataset_id: str = "BOP_ITS6_DET"):
        super().__init__(dataset_id)

    def get_data(
        self,
        geo:          str = "DK",
        partner:      str = "WRL_REST",
        bop_item:     str = "S",
        stk_flow:     str = "CRE+DEB",
        currency:     str = "MIO_EUR",
        freq:         str = "A",
        start_period: str = "2015",
        end_period:   str | None = None,
    ) -> pd.DataFrame:
        """
        Fetch international trade in services data and return a tidy pandas DataFrame.

        Use '+' to combine multiple values per dimension, e.g.
            geo      = "DK+DE+FR"
            bop_item = "SC+SD+SE"

        Parameters
        ----------
        geo          : ISO-2 reporter country code(s), e.g. 'DK'
        partner      : partner country/region — use api.codes('partner', aggregates_only=True)
        bop_item     : EBOPS 2010 service category — use api.codes('bop_item', search=...)
                       'S'=total services, 'SC'=transport, 'SD'=travel, 'SE'=other
        stk_flow     : CRE=credit/exports, DEB=debit/imports, BAL=balance
        currency     : MIO_EUR (default) or MIO_NAC
        freq         : A=annual, Q=quarterly
        start_period : e.g. '2015' (annual) or '2015-Q1' (quarterly)
        end_period   : optional, e.g. '2023'
        """
        key = f"{freq}.{currency}.{bop_item}.{stk_flow}.{partner}.{geo}"
        url = f"{self._BASE}/data/{self.dataset_id}/{key}"
        params: dict = {"format": "JSON", "startPeriod": start_period, "compressed": "true"}
        if end_period:
            params["endPeriod"] = end_period

        r = _session.get(url, params=params, timeout=300)
        r.raise_for_status()

        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8"))

        return self._jsonstat_to_df(data)
