"""What the API says when its database is down: a clear 503 the website can explain, not a crash."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app
from tests.conftest import new_client


def test_database_down_gives_clear_503_on_every_endpoint():
    # Nothing listens on port 1, so every query fails to connect, just like a stopped PostgreSQL.
    dead_engine = create_engine("postgresql+psycopg://foodloop:x@127.0.0.1:1/foodloop", pool_pre_ping=False)
    dead_session = sessionmaker(bind=dead_engine)

    def broken_db():
        with dead_session() as session:
            yield session

    app.dependency_overrides[get_db] = broken_db
    try:
        client = new_client()
        response = client.get("/api/listings")
        assert response.status_code == 503
        body = response.json()
        assert body["code"] == "database_unavailable"
        assert "database" in body["detail"]
        assert client.get("/api/health").json() == {"status": "error", "database": "unreachable"}
    finally:
        app.dependency_overrides.pop(get_db, None)
        dead_engine.dispose()
