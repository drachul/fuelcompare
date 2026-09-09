from flask import Blueprint, jsonify, request

from . import epa_client
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


@bp.post("/compare")
def compare():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(compute_comparison(payload))
    except CalcError as exc:
        return jsonify({"error": str(exc)}), 400
