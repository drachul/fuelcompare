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
public API (no API key required, covers model years back to 1984). Tank size
isn't published by that API, so it's entered manually per vehicle.

## Run with Docker Compose

```bash
docker compose up --build
```

Then open http://localhost:8080. Stop with `docker compose down`.

## Run with Docker (no Compose)

```bash
docker build -t fuelcompare .
docker run --rm -p 8080:8080 fuelcompare
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
  fast and avoid hammering fueleconomy.gov.
