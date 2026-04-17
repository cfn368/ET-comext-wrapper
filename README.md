# comext_wrapper

A Python wrapper for the [Eurostat Comext SDMX 2.1 API](https://ec.europa.eu/eurostat/databrowser/product/view/ds-045409) (dataset DS-045409: EU trade by HS2/4/6 and CN8).

## Install

```bash
pip install comext_wrapper
```

## Usage

```python
from comext_wrapper import ComextApi

api = ComextApi()
api.info()                          # dataset overview + dimension list
api.codes("reporter")               # all valid reporter codes
api.codes("product", search="wind") # search CN codes by label
api.codes("indicators")             # available value indicators

df = api.get_data(
    reporter     = "DE+FR+DK",
    partner      = "EXT_EU27_2020",   # extra-EU aggregate
    product      = "85024000+85017100",
    flow         = "1+2",             # 1=import, 2=export
    indicators   = "VALUE_IN_EUROS",
    start_period = "2020-01",
)
```

`get_data` returns a tidy `pandas.DataFrame` with one row per (reporter, partner, product, flow, period) combination and a `value` column.

Use `+` to query multiple codes in a single request:

```python
df = api.get_data(
    reporter = "DE+FR+SE+DK+FI+NO",
    product  = "85024000+85017100+85018000+85044000",
    flow     = "1+2",
    start_period = "2015-01",
    end_period   = "2024-12",
)
```

## Dimensions

| Dimension   | Description                        | Example values              |
|-------------|------------------------------------|-----------------------------|
| `reporter`  | Reporting country (ISO-2 or group) | `DE`, `EU`                  |
| `partner`   | Partner country / aggregate        | `EXT_EU27_2020`, `US`       |
| `product`   | 8-digit CN product code            | `85024000` (wind turbines)  |
| `flow`      | Trade flow                         | `1`=import, `2`=export      |
| `indicators`| Value type                         | `VALUE_IN_EUROS`, `QUANTITY_IN_100KG` |
| `freq`      | Frequency                          | `M`=monthly, `A`=annual     |
