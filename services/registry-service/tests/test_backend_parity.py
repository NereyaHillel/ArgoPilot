import threading

from support import plot_payload

# These run on whichever backend the suite targets, so both must give the same answers.

LONG_NAME = "z" * 10_000
INJECTION = "'; DROP TABLE farms;--"
FARM_NAMES = ["banana", "😀", LONG_NAME, "Apple", INJECTION, "éclair"]
# Byte-wise UTF-8 order, as SQLite compares text.
BYTEWISE_ORDER = [INJECTION, "Apple", "banana", LONG_NAME, "éclair", "😀"]


def test_farm_list_is_ordered_bytewise_and_names_round_trip(client):
    for name in FARM_NAMES:
        assert client.post("/v1/farms", json={"name": name}).status_code == 201

    listed = [farm["name"] for farm in client.get("/v1/farms").json()]

    created = [name for name in listed if name in FARM_NAMES]
    assert created == BYTEWISE_ORDER
    assert created == sorted(FARM_NAMES, key=lambda name: name.encode())


def test_floats_round_trip_exactly(client):
    payload = plot_payload(area_m2=1234.5678901234567, lat=31.123456789012345)

    created = client.post("/v1/plots", json=payload).json()
    fetched = client.get(f"/v1/plots/{created['id']}").json()

    for body in (created, fetched):
        assert body["area_m2"] == 1234.5678901234567
        assert body["lat"] == 31.123456789012345


def test_concurrent_creates_with_same_plot_name_give_one_201_and_one_409(client):
    barrier = threading.Barrier(2)
    responses = []

    def create():
        barrier.wait()
        responses.append(client.post("/v1/plots", json=plot_payload(name="Race block")))

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(response.status_code for response in responses) == [201, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["code"] == "CONFLICT"
