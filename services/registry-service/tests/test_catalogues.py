import pytest

CATALOGUE_PATHS = [
    "/v1/crops",
    "/v1/crops/tomato",
    "/v1/soils",
    "/v1/soils/loam",
    "/v1/emitters",
    "/v1/emitters/dripnet-pc-1.0",
]


def test_list_crops_returns_seeded_crops(client):
    response = client.get("/v1/crops")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "bell-pepper", "name": "Bell pepper"},
        {"id": "tomato", "name": "Tomato"},
    ]


def test_get_crop_returns_200(client):
    response = client.get("/v1/crops/tomato")

    assert response.status_code == 200
    assert response.json() == {"id": "tomato", "name": "Tomato"}


def test_unknown_crop_returns_404(client):
    response = client.get("/v1/crops/ghost")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_list_soils_returns_seeded_soils(client):
    response = client.get("/v1/soils")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "clay-loam", "name": "Clay loam", "available_water_mm_per_m": 200},
        {"id": "loam", "name": "Loam", "available_water_mm_per_m": 175},
        {"id": "sand", "name": "Sand", "available_water_mm_per_m": 83},
    ]


def test_get_soil_returns_200(client):
    response = client.get("/v1/soils/sand")

    assert response.status_code == 200
    assert response.json() == {"id": "sand", "name": "Sand", "available_water_mm_per_m": 83}


def test_unknown_soil_returns_404(client):
    response = client.get("/v1/soils/ghost")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_list_emitters_returns_seeded_emitters(client):
    response = client.get("/v1/emitters")

    assert response.status_code == 200
    assert [emitter["id"] for emitter in response.json()] == [
        "dripnet-pc-0.6",
        "dripnet-pc-1.0",
        "dripnet-pc-1.6",
        "dripnet-pc-2.0",
    ]


def test_get_emitter_returns_200(client):
    response = client.get("/v1/emitters/dripnet-pc-1.0")

    assert response.status_code == 200
    assert response.json() == {"id": "dripnet-pc-1.0", "name": "DripNet PC", "flow_lph": 1.0}


def test_unknown_emitter_returns_404(client):
    response = client.get("/v1/emitters/ghost")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize("path", CATALOGUE_PATHS)
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_non_get_methods_on_catalogues_return_405(client, path, method):
    response = client.request(method, path)

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "VALIDATION"


@pytest.mark.parametrize("path", CATALOGUE_PATHS)
def test_head_on_catalogues_returns_405(client, path):
    response = client.head(path)

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
