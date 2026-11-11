import uuid

import pytest
from support import (
    FARM_DEMO,
    FARM_EAST,
    PLOT_EAST,
    PLOT_GREENHOUSE,
    PLOT_NORTH,
    PLOT_WEST,
    UNKNOWN_ID,
)


def test_create_farm_returns_201_with_only_spec_fields(client):
    response = client.post("/v1/farms", json={"name": "New farm"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name"}
    assert body["name"] == "New farm"
    assert str(uuid.UUID(body["id"])) == body["id"]


def test_created_farm_can_be_fetched(client):
    created = client.post("/v1/farms", json={"name": "New farm"}).json()

    response = client.get(f"/v1/farms/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_list_farms_returns_seeded_farms(client):
    response = client.get("/v1/farms")

    assert response.status_code == 200
    assert {farm["id"] for farm in response.json()} == {FARM_DEMO, FARM_EAST}


def test_list_farms_is_sorted_by_name(client):
    client.post("/v1/farms", json={"name": "Aardvark farm"})

    names = [farm["name"] for farm in client.get("/v1/farms").json()]

    assert names == sorted(names)


def test_get_farm_returns_seeded_values(client):
    response = client.get(f"/v1/farms/{FARM_DEMO}")

    assert response.status_code == 200
    assert response.json() == {"id": FARM_DEMO, "name": "Demo cooperative"}


def test_get_unknown_farm_returns_404(client):
    response = client.get(f"/v1/farms/{UNKNOWN_ID}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_patch_updates_only_provided_fields(client):
    response = client.patch(f"/v1/farms/{FARM_EAST}", json={"name": "Renamed"})

    assert response.status_code == 200
    assert response.json() == {"id": FARM_EAST, "name": "Renamed"}
    assert client.get(f"/v1/farms/{FARM_EAST}").json() == {"id": FARM_EAST, "name": "Renamed"}


def test_patch_with_empty_body_changes_nothing(client):
    response = client.patch(f"/v1/farms/{FARM_EAST}", json={})

    assert response.status_code == 200
    assert response.json() == {"id": FARM_EAST, "name": "East farm"}


def test_patch_unknown_farm_returns_404(client):
    response = client.patch(f"/v1/farms/{UNKNOWN_ID}", json={"name": "Ghost"})

    assert response.status_code == 404


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_farm_name_is_rejected(client, name):
    response = client.post("/v1/farms", json={"name": name})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"


def test_farm_name_of_255_characters_is_accepted(client):
    response = client.post("/v1/farms", json={"name": "f" * 255})

    assert response.status_code == 201
    assert response.json()["name"] == "f" * 255


def test_farm_name_of_256_characters_is_rejected(client):
    response = client.post("/v1/farms", json={"name": "f" * 256})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION"
    assert response.json()["detail"] == "name: String should have at most 255 characters"


def test_patch_rejects_null_name(client):
    response = client.patch(f"/v1/farms/{FARM_EAST}", json={"name": None})

    assert response.status_code == 422
    assert response.json()["detail"] == "name: must not be null"


def test_delete_farm_without_plots_returns_204(client):
    farm_id = client.post("/v1/farms", json={"name": "Temporary"}).json()["id"]

    response = client.delete(f"/v1/farms/{farm_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/v1/farms/{farm_id}").status_code == 404


def test_delete_farm_with_plots_returns_409_and_keeps_it(client):
    response = client.delete(f"/v1/farms/{FARM_DEMO}")

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"
    assert client.get(f"/v1/farms/{FARM_DEMO}").status_code == 200


def test_delete_unknown_farm_returns_404(client):
    assert client.delete(f"/v1/farms/{UNKNOWN_ID}").status_code == 404


def test_empty_collections_return_200_and_empty_arrays(client):
    for plot_id in (PLOT_NORTH, PLOT_EAST, PLOT_WEST, PLOT_GREENHOUSE):
        assert client.delete(f"/v1/plots/{plot_id}").status_code == 204
    for farm_id in (FARM_DEMO, FARM_EAST):
        assert client.delete(f"/v1/farms/{farm_id}").status_code == 204

    farms = client.get("/v1/farms")
    plots = client.get("/v1/plots")

    assert (farms.status_code, farms.json()) == (200, [])
    assert (plots.status_code, plots.json()) == (200, [])
