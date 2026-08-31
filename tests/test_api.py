import pytest
from fastapi.testclient import TestClient

from app.linkedin.errors import LinkedInBlocked, ProfileNotFound
from app.main import app, get_service
from app.models import Profile, VoyagerStatus


class FakeService:
    def health(self) -> VoyagerStatus:
        return VoyagerStatus(configured=False, session="unconfigured")

    def get_profile(self, public_id: str) -> Profile:
        if public_id == "missing-person":
            raise ProfileNotFound("Profile not found")
        if public_id == "blocked-person":
            raise LinkedInBlocked("blocked")
        return Profile(
            source="guest",
            url=f"https://www.linkedin.com/in/{public_id}/",
            public_id=public_id,
            full_name="Ada Lovelace",
        )


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_service] = lambda: FakeService()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["voyager"]["configured"] is False


def test_get_profile(client: TestClient) -> None:
    response = client.get(
        "/v1/profile",
        params={"url": "https://www.linkedin.com/in/ada-lovelace/"},
    )
    assert response.status_code == 200
    assert response.json()["public_id"] == "ada-lovelace"
    assert response.json()["source"] == "guest"


def test_post_profile(client: TestClient) -> None:
    response = client.post(
        "/v1/profile",
        json={"url": "https://www.linkedin.com/in/ada-lovelace"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Ada Lovelace"


def test_invalid_url(client: TestClient) -> None:
    response = client.get(
        "/v1/profile",
        params={"url": "https://www.linkedin.com/company/google"},
    )
    assert response.status_code == 400


def test_not_found(client: TestClient) -> None:
    response = client.get(
        "/v1/profile",
        params={"url": "https://www.linkedin.com/in/missing-person"},
    )
    assert response.status_code == 404


def test_blocked(client: TestClient) -> None:
    response = client.get(
        "/v1/profile",
        params={"url": "https://www.linkedin.com/in/blocked-person"},
    )
    assert response.status_code == 502
