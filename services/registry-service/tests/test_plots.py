import json
from datetime import UTC, datetime, timedelta

import pytest
from support import (
    FARM_DEMO,
    FARM_EAST,
    PLOT_EAST,
    PLOT_GREENHOUSE,
    PLOT_NORTH,
    PLOT_WEST,
    UNKNOWN_ID,
    plot_payload,
)

NORTH_BLOCK = {
    "id": PLOT_NORTH,
    "farm_id": FARM_DEMO,
    "name": "North block",
    "area_m2": 1000.0,
    "crop_id": "tomato",
    "planting_date": "2026-03-01",
    "soil_id": "loam",
    "row_spacing_m": 1.5,
    "emitter_spacing_m": 0.4,
    "emitter_id": "dripnet-pc-1.0",
    "lat": 31.25,
    "lon": 34.79,
}


def utc_today():
    return datetime.now(UTC).date()


def test_create_plot_returns_201_with_only_spec_fields(client):
    response = client.post("/v1/plots", json=plot_payload())

    assert response.status_code == 201
    body = response.json()
    assert set(body) == set(NORTH_BLOCK)
    assert body["farm_id"] == FARM_DEMO
    assert body["planting_date"] == "2026-03-01"


def test_created_plot_can_be_fetched(client):
    created = client.post("/v1/plots", json=plot_payload()).json()

    assert client.get(f"/v1/plots/{created['id']}").json() == created


def test_get_plot_returns_seeded_values(client):
    response = client.get(f"/v1/plots/{PLOT_NORTH}")

    assert response.status_code == 200
    assert response.json() == NORTH_BLOCK


def test_get_unknown_plot_returns_404(client):
    response = client.get(f"/v1/plots/{UNKNOWN_ID}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_list_plots_without_filter_returns_every_plot(client):
    response = client.get("/v1/plots")

    assert response.status_code == 200
    assert {plot["id"] for plot in response.json()} == {
        PLOT_NORTH,
        PLOT_EAST,
        PLOT_WEST,
        PLOT_GREENHOUSE,
    }


def test_list_plots_filtered_by_farm(client):
    response = client.get("/v1/plots", params={"farm_id": FARM_DEMO})

    assert response.status_code == 200
    assert {plot["id"] for plot in response.json()} == {PLOT_NORTH, PLOT_EAST}


def test_list_plots_for_unknown_farm_is_empty(client):
    response = client.get("/v1/plots", params={"farm_id": UNKNOWN_ID})

    assert response.status_code == 200
    assert response.json() == []


def test_patch_updates_only_provided_fields(client):
    response = client.patch(f"/v1/plots/{PLOT_NORTH}", json={"area_m2": 1200, "lat": 31.3})

    assert response.status_code == 200
    assert response.json() == {**NORTH_BLOCK, "area_m2": 1200.0, "lat": 31.3}


def test_patch_can_move_plot_to_another_farm(client):
    response = client.patch(f"/v1/plots/{PLOT_NORTH}", json={"farm_id": FARM_EAST})

    assert response.status_code == 200
    assert response.json()["farm_id"] == FARM_EAST


def test_patch_keeping_own_name_is_not_a_conflict(client):
    response = client.patch(f"/v1/plots/{PLOT_NORTH}", json={"name": "North block"})

    assert response.status_code == 200


def test_patch_rename_to_name_used_on_same_farm_is_409(client):
    response = client.patch(f"/v1/plots/{PLOT_NORTH}", json={"name": "East block"})

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_patch_move_into_name_taken_on_new_farm_is_409(client):
    client.post("/v1/plots", json=plot_payload(farm_id=FARM_EAST, name="North block"))

    response = client.patch(f"/v1/plots/{PLOT_NORTH}", json={"farm_id": FARM_EAST})

    assert response.status_code == 409
    assert client.get(f"/v1/plots/{PLOT_NORTH}").json()["farm_id"] == FARM_DEMO


def test_patch_with_unknown_reference_is_422(client):
    response = client.patch(f"/v1/plots/{PLOT_NORTH}", json={"crop_id": "ghost"})

    assert response.status_code == 422
    assert response.json()["detail"] == "crop_id: unknown crop 'ghost'"


def test_patch_rejects_null_and_unknown_fields_without_changing_plot(client):
    null_response = client.patch(f"/v1/plots/{PLOT_NORTH}", json={"area_m2": None})
    typo_response = client.patch(f"/v1/plots/{PLOT_NORTH}", json={"aera_m2": 5})

    assert null_response.status_code == 422
    assert null_response.json()["detail"] == "area_m2: must not be null"
    assert typo_response.status_code == 422
    assert typo_response.json()["detail"] == "aera_m2: Extra inputs are not permitted"
    assert client.get(f"/v1/plots/{PLOT_NORTH}").json() == NORTH_BLOCK


def test_plot_name_may_repeat_on_another_farm(client):
    response = client.post("/v1/plots", json=plot_payload(farm_id=FARM_EAST, name="North block"))

    assert response.status_code == 201


def test_plot_name_must_be_unique_within_its_farm(client):
    response = client.post("/v1/plots", json=plot_payload(farm_id=FARM_DEMO, name="North block"))

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


def test_plot_name_uniqueness_is_case_sensitive(client):
    response = client.post("/v1/plots", json=plot_payload(farm_id=FARM_DEMO, name="north block"))

    assert response.status_code == 201


def test_list_plots_is_sorted_by_name(client):
    names = [plot["name"] for plot in client.get("/v1/plots").json()]

    assert names == sorted(names)


def test_delete_plot_returns_204_then_404(client):
    assert client.delete(f"/v1/plots/{PLOT_WEST}").status_code == 204
    assert client.get(f"/v1/plots/{PLOT_WEST}").status_code == 404
    assert client.delete(f"/v1/plots/{PLOT_WEST}").status_code == 404


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("area_m2", 0),
        ("area_m2", -1),
        ("row_spacing_m", 0),
        ("emitter_spacing_m", -0.4),
        ("lat", 90.5),
        ("lat", -91),
        ("lon", 180.1),
        ("lon", -180.5),
    ],
)
def test_out_of_range_values_are_rejected(client, field, value):
    response = client.post("/v1/plots", json=plot_payload(**{field: value}))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"
    assert response.json()["detail"].startswith(f"{field}: ")


@pytest.mark.parametrize(("field", "value"), [("area_m2", "1000"), ("lat", "31.25")])
def test_numeric_strings_are_rejected(client, field, value):
    response = client.post("/v1/plots", json=plot_payload(**{field: value}))

    assert response.status_code == 422


def test_infinite_area_is_rejected(client):
    # json.dumps writes inf as the non-standard token Infinity, which the server must refuse.
    body = json.dumps(plot_payload(area_m2=float("inf")))

    response = client.post("/v1/plots", content=body, headers={"content-type": "application/json"})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [("lat", 90), ("lat", -90), ("lon", 180), ("lon", -180), ("area_m2", 0.01)],
)
def test_boundary_values_are_accepted(client, field, value):
    response = client.post(
        "/v1/plots", json=plot_payload(name=f"{field} {value}", **{field: value})
    )

    assert response.status_code == 201


def test_planting_date_of_today_in_utc_is_accepted(client):
    response = client.post("/v1/plots", json=plot_payload(planting_date=utc_today().isoformat()))

    assert response.status_code == 201


def test_future_planting_date_is_rejected(client):
    tomorrow = (utc_today() + timedelta(days=1)).isoformat()

    response = client.post("/v1/plots", json=plot_payload(planting_date=tomorrow))

    assert response.status_code == 422
    assert response.json()["detail"] == "planting_date: Planting date cannot be in the future"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("farm_id", UNKNOWN_ID),
        ("crop_id", "ghost"),
        ("soil_id", "ghost"),
        ("emitter_id", "ghost"),
    ],
)
def test_unknown_reference_is_rejected(client, field, value):
    response = client.post("/v1/plots", json=plot_payload(**{field: value}))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"
    assert response.json()["detail"].startswith(f"{field}: unknown")


def test_every_failing_field_is_reported(client):
    response = client.post("/v1/plots", json=plot_payload(area_m2=0, lat=95))

    assert response.json()["detail"] == (
        "area_m2: Input should be greater than 0; lat: Input should be less than or equal to 90"
    )


def test_missing_required_field_is_rejected(client):
    payload = plot_payload()
    del payload["emitter_id"]

    response = client.post("/v1/plots", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "emitter_id: Field required"


def test_blank_plot_name_is_rejected(client):
    response = client.post("/v1/plots", json=plot_payload(name="  "))

    assert response.status_code == 422
