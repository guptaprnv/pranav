import pytest
from fastapi.testclient import TestClient

from quant_primitives.api.main import app
from quant_primitives.fixtures.generate import ENTITIES

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_entities_matches_fixture_reference_data():
    response = client.get("/primitives/entities")
    assert response.status_code == 200
    entity_ids = {row["entity_id"] for row in response.json()}
    assert entity_ids == set(ENTITIES)


@pytest.mark.parametrize("entity_id", list(ENTITIES))
def test_per_entity_primitives_return_a_grounded_result(entity_id):
    for path in (
        f"/primitives/{entity_id}/return",
        f"/primitives/{entity_id}/alpha-beta",
        f"/primitives/{entity_id}/var",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        body = response.json()
        # every primitive result carries these regardless of the specific
        # value -- this is the citation/auditability contract, not a detail
        assert body["pipeline_version"]
        assert body["computed_at"]
        assert body["input_as_of"]
        assert body["confidence"] in {"high", "medium", "low"}


def test_unknown_entity_is_a_404_not_a_500():
    response = client.get("/primitives/NOT_A_REAL_ISIN/return")
    assert response.status_code == 404


def test_portfolio_level_primitives():
    for path in (
        "/primitives/portfolio/correlation",
        "/primitives/portfolio/drift",
        "/primitives/portfolio/concentration",
    ):
        response = client.get(path)
        assert response.status_code == 200, path


def test_portfolio_concentration_rejects_unknown_level():
    response = client.get("/primitives/portfolio/concentration", params={"level": "bogus"})
    assert response.status_code == 400
