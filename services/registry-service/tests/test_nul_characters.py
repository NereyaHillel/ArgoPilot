import pytest
from support import FARM_DEMO, PLOT_NORTH, plot_payload

NUL_VALUE = "a\u0000b"
PLOT_TEXT_FIELDS = ["name", "crop_id", "soil_id", "emitter_id"]


def assert_nul_rejected(response, field):
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION"
    assert body["detail"] == f"{field}: must not contain NUL characters"


def test_create_farm_rejects_nul_in_name(client):
    response = client.post("/v1/farms", json={"name": NUL_VALUE})

    assert_nul_rejected(response, "name")


def test_update_farm_rejects_nul_in_name(client):
    response = client.patch(f"/v1/farms/{FARM_DEMO}", json={"name": NUL_VALUE})

    assert_nul_rejected(response, "name")


@pytest.mark.parametrize("field", PLOT_TEXT_FIELDS)
def test_create_plot_rejects_nul(client, field):
    response = client.post("/v1/plots", json=plot_payload(**{field: NUL_VALUE}))

    assert_nul_rejected(response, field)


@pytest.mark.parametrize("field", PLOT_TEXT_FIELDS)
def test_update_plot_rejects_nul(client, field):
    response = client.patch(f"/v1/plots/{PLOT_NORTH}", json={field: NUL_VALUE})

    assert_nul_rejected(response, field)


def test_name_without_nul_is_still_accepted(client):
    response = client.post("/v1/farms", json={"name": "ab"})

    assert response.status_code == 201
