# Fuel Compare

A small web app for comparing the annual fuel cost of different vehicles, based
on driving distance, city/highway mix, and local fuel prices. It reproduces
the math from the original "fuel mileage comparison" spreadsheet:

```
overall L/100km  = city L/100km * city% + highway L/100km * highway%
range per tank   = tank size (L) / overall L/100km * 100
cost per tank    = tank size (L) * price per liter
fill-ups / year  = annual km / range per tank
annual fuel cost = fill-ups per year * cost per tank
```

Vehicle city/highway consumption and fuel type are looked up for free from the
US DOE/EPA [fueleconomy.gov](https://www.fueleconomy.gov/feg/ws/index.shtml)
public API (no API key required, covers model years back to 1984). That API has
no tank-capacity field, so the app also does a best-effort lookup against
[CarAPI](https://carapi.app/). It ranks same-year/make/model records using
engine, transmission, and EPA MPG data. A clear match is pre-filled; ambiguous
matches are offered as suggestions, and the field always remains editable.

CarAPI's unauthenticated demo data covers model years 2015-2020. To enable its
full subscribed dataset, set `CARAPI_API_TOKEN` and `CARAPI_API_SECRET` in the
app environment. The app obtains and caches the short-lived JWT automatically;
credentials and tokens are never sent to the browser.

Fuel-price fields can be primed from the latest monthly city averages in
Statistics Canada [table 18-10-0001-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000101).
The app loads regular, premium, and diesel self-service prices in CAD/litre.
Statistics Canada does not publish midgrade in this table, so that value is
left untouched. All price fields remain editable, and the UI links to Natural
Resources Canada's current fuel-price page as a manual lookup fallback.

Vehicle details are stored in a local SQLite cache after an EPA lookup or a
successful comparison. That includes tank-size lookup results and manual
changes. Saved vehicles can be loaded into any comparison card without calling
the external vehicle APIs again.

## Run with Docker Compose

```bash
docker compose up --build
```

Then open http://localhost:8080. Stop with `docker compose down`.

The Compose configuration keeps the SQLite database at
`./data/fuelcompare.db`, so saved vehicles survive container recreation and
the database remains directly accessible from the project directory.

## Run with Docker (no Compose)

```bash
docker build -t fuelcompare .
mkdir -p data
docker run --rm -p 8080:8080 \
  -e FUELCOMPARE_DB_PATH=/app/data/fuelcompare.db \
  -v "$(pwd)/data:/app/data" fuelcompare
```

Then open http://localhost:8080

## Run locally without Docker

```bash
pip install -r requirements.txt
python app.py
```

## Notes

- Only gasoline (regular/midgrade/premium) and diesel vehicles are supported
  for cost calculations, matching the original spreadsheet. Electric/hybrid-
  plug-in/CNG/hydrogen/flex-fuel trims are flagged as unsupported when picked
  from the EPA dropdowns — you can still fill in the fields manually.
- EPA API responses are cached in memory for 24 hours to keep the dropdowns
  fast and avoid hammering fueleconomy.gov. Selected vehicle records are also
  cached persistently in SQLite. Set `FUELCOMPARE_DB_PATH` to choose a different
  database location; locally it defaults to `data/fuelcompare.db`.
- Statistics Canada data are also cached in memory for 24 hours. If that
  service cannot be reached, fuel prices can still be entered manually.
- Tank-size matches are estimates because the EPA and CarAPI trim identifiers
  are not directly compatible. Verify a suggested size against the vehicle's
  owner's manual. When no single size can be selected automatically, the UI
  also links to the vehicle's make/model/year page on
  [FuelTankCap](https://fueltankcap.com/) for manual lookup.
