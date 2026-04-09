# Green Tech Trade Balance

Monthly EU extra-trade data for selected green-tech product categories (wind, solar, heat pumps, batteries, EVs), sourced from [Eurostat](https://ec.europa.eu/eurostat/databrowser/product/view/ds-045409?category=ext_go.ext_go_detail) via their SDMX 2.1 API.

## Notebooks

| Notebook | Purpose |
|----------|---------|
| `0_lookup.ipynb` | Explore the Comext API — browse dimensions, search product codes, test queries |
| `1_clean_tech.ipynb` | Fetch, aggregate and plot the trade balance by category |

## Output

- `clean_tech_trade_balance.png` — stacked bar chart (exports positive, imports negative)
- `clean_tech_trade_balance.xlsx` — monthly data in wide format

## Setup

```bash
pip install requests pandas matplotlib openpyxl
```

## Key files

- `pylib/comext.py` — `ComextApi` helper class for the Eurostat Comext SDMX API
- `pylib/groups.py` — product code lists and reporter country lists