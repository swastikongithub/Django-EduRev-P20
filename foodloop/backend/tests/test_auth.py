from tests.conftest import PASSWORD, new_client, unique_email


def register(client, **overrides):
    payload = {"email": unique_email(), "password": PASSWORD, "full_name": "Riya Sharma"}
    payload.update(overrides)
    return client.post("/api/auth/register", json=payload)


def test_health_and_meta(client):
    assert client.get("/api/health").json() == {"status": "ok", "database": "ok"}
    meta = client.get("/api/meta").json()
    assert meta["labels"]["diet"]["veg"] == "Veg"
    assert meta["safety_policy"]["max_safe_hours"]["room_temp"] == 2


def test_register_logs_in_with_secure_cookie(client):
    response = register(client, email="Riya@Example.com")
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "riya@example.com"  # stored lower-case
    assert response.json()["user"]["role"] == "customer"
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header and "samesite=lax" in cookie_header
    assert client.get("/api/auth/me").json()["user"]["full_name"] == "Riya Sharma"


def test_duplicate_email_is_rejected(client):
    email = unique_email()
    assert register(client, email=email).status_code == 201
    response = register(new_client(), email=email.upper())
    assert response.status_code == 409
    assert response.json()["errors"][0]["field"] == "email"


def test_weak_password_is_rejected(client):
    response = register(client, password="password")
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "password"
    assert register(client, password="short").status_code == 422


def test_login_logout_flow(client):
    email = unique_email()
    register(new_client(), email=email)
    assert client.post("/api/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").json()["user"]["email"] == email
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json() is None


def test_unknown_email_gets_same_message_as_wrong_password(client):
    response = client.post("/api/auth/login", json={"email": unique_email(), "password": PASSWORD})
    assert response.status_code == 401
    assert response.json()["detail"] == "That email and password don't match. Please try again."


def test_login_is_rate_limited(client):
    email = unique_email()
    register(new_client(), email=email)
    for _ in range(10):
        client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 429


def test_cross_site_post_is_blocked(client):
    response = client.post(
        "/api/auth/register",
        json={"email": unique_email(), "password": PASSWORD, "full_name": "Evil"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    allowed = register(client, email=unique_email())
    assert allowed.status_code == 201


def test_security_headers(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
