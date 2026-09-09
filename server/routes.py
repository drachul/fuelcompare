from flask import Blueprint, jsonify, request

from . import carapi_client, epa_client, statcan_client
from .calc import CalcError, compute_comparison

bp = Blueprint("api", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/years")
def years():
    try:
        return jsonify(epa_client.get_years())
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/makes")
def makes():
    year = request.args.get("year", "")
    if not year:
        return jsonify({"error": "year is required"}), 400
    try:
        return jsonify(epa_client.get_makes(year))
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/models")
def models():
    year = request.args.get("year", "")
    make = request.args.get("make", "")
    if not year or not make:
        return jsonify({"error": "year and make are required"}), 400
    try:
        return jsonify(epa_client.get_models(year, make))
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/trims")
def trims():
    year = request.args.get("year", "")
    make = request.args.get("make", "")
    model = request.args.get("model", "")
    if not year or not make or not model:
        return jsonify({"error": "year, make and model are required"}), 400
    try:
        return jsonify(epa_client.get_trims(year, make, model))
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/vehicle/<vehicle_id>")
def vehicle(vehicle_id):
    try:
        return jsonify(epa_client.get_vehicle(vehicle_id))
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/fuel-price-locations")
def fuel_price_locations():
    try:
        return jsonify(statcan_client.get_locations())
    except statcan_client.StatsCanApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/fuel-prices")
def fuel_prices():
    location = request.args.get("location", "").strip()
    if not location:
        return jsonify({"error": "location is required"}), 400
    try:
        return jsonify(statcan_client.get_latest_prices(location))
    except statcan_client.UnknownLocationError as exc:
        return jsonify({"error": str(exc)}), 404
    except statcan_client.StatsCanApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/tank-size")
def tank_size():
    year = request.args.get("year", "")
    make = request.args.get("make", "")
    model = request.args.get("model", "")
    cylinders = request.args.get("cylinders", "")
    displ = request.args.get("displ", "")
    city_mpg = request.args.get("city_mpg", "")
    highway_mpg = request.args.get("highway_mpg", "")
    transmission = request.args.get("transmission", "")
    base_model = request.args.get("base_model", "")
    if not year or not make or not model:
        return jsonify({"error": "year, make and model are required"}), 400
    return jsonify(
        carapi_client.find_tank_capacity(
            year,
            make,
            model,
            cylinders,
            displ,
            city_mpg,
            highway_mpg,
            transmission,
            base_model,
        )
    )


@bp.post("/compare")
def compare():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(compute_comparison(payload))
    except CalcError as exc:
        return jsonify({"error": str(exc)}), 400
