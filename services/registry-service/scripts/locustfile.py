import random
from locust import HttpUser, task, constant

class AgroPilotUser(HttpUser):
    # Each user waits exactly 1 second between requests.
    # 10 users * 1 request/second = 10 RPS.
    wait_time = constant(1)

    @task
    def test_get_endpoints(self):
        # A mix of list and by-ID reads, mimicking real downstream microservice behavior
        endpoints = [
            "/v1/farms",
            "/v1/plots",
            "/v1/crops",
            "/v1/soils",
            "/v1/emitters",
            "/v1/crops/tomato",
            "/v1/soils/sand",
            "/v1/emitters/dripnet-pc-1.0",
            "/v1/farms/b7e2c0a0-3c1d-4f0a-9a11-0c5d2e6f1001",
            "/v1/plots/c8f3d1b0-4d2e-5a1b-8b22-1d6e3f702002"
        ]
        endpoint = random.choice(endpoints)

        # Name the request broadly in Locust's UI so it groups them logically,
        # otherwise Locust tracks every unique ID as a separate row.
        with self.client.get(endpoint, catch_response=True, name="GET Read-Only Endpoints") as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")
