import importlib
import json

from werkzeug.security import generate_password_hash

from retrostation_player.config import DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

def test_auth_disabled_by_default():
    assert DEFAULT_CONFIG["auth_enabled"] is False


def test_auth_default_username_is_admin():
    assert DEFAULT_CONFIG["auth_username"] == "admin"


def test_auth_default_password_hash_is_empty():
    assert DEFAULT_CONFIG["auth_password_hash"] == ""


def test_secret_key_default_is_empty():
    assert DEFAULT_CONFIG["secret_key"] == ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_PASSWORD = "testpassword123"


def _make_app(monkeypatch, tmp_path, *, auth_enabled=False, username="admin", password=_TEST_PASSWORD, must_change_password=False):
    """Create a Flask test client with optional auth pre-configured."""
    monkeypatch.setenv("RETROSTATION_PLAYER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETROSTATION_PLAYER_STATE_DIR", str(tmp_path / "state"))

    if auth_enabled and password is not None:
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "auth_enabled": True,
            "auth_username": username,
            "auth_password_hash": generate_password_hash(password),
            "secret_key": "test-secret-key-32-chars-exactly!!",
            "auth_must_change_password": must_change_password,
        }
        (config_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")

    app_module = importlib.import_module("retrostation_player.app")
    monkeypatch.setattr("retrostation_player.player.state_file", lambda: tmp_path / "state" / "state.json")
    app = app_module.create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    return client


# ---------------------------------------------------------------------------
# Auth disabled (default behaviour)
# ---------------------------------------------------------------------------

def test_index_accessible_without_auth_when_disabled(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=False)
    response = client.get("/")
    assert response.status_code == 200


def test_api_health_always_accessible(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=False)
    response = client.get("/api/health")
    assert response.status_code == 200


def test_login_redirects_to_index_when_auth_disabled(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=False)
    response = client.get("/login")
    assert response.status_code in (301, 302)
    assert "/" in response.headers["Location"]


# ---------------------------------------------------------------------------
# Auth enabled - unauthenticated access
# ---------------------------------------------------------------------------

def test_index_redirects_to_login_when_auth_enabled(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    response = client.get("/")
    assert response.status_code in (301, 302)
    assert "login" in response.headers["Location"]


def test_api_returns_401_when_auth_enabled_and_not_logged_in(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    response = client.get("/api/channels", headers={"Accept": "application/json"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "Authentication required"


def test_api_health_accessible_without_login_when_auth_enabled(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    response = client.get("/api/health")
    assert response.status_code == 200


def test_login_page_renders_when_auth_enabled(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Sign In" in response.data


def test_authenticated_index_page_shows_logout_button(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    client.post("/login", data={"username": "admin", "password": _TEST_PASSWORD})
    response = client.get("/")
    assert response.status_code == 200
    assert b"Logout" in response.data
    assert b"/logout" in response.data


# ---------------------------------------------------------------------------
# Auth enabled - login flow
# ---------------------------------------------------------------------------

def test_login_with_correct_credentials_grants_access(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    with client.session_transaction() as sess:
        assert not sess.get("authenticated")

    post = client.post(
        "/login",
        data={"username": "admin", "password": _TEST_PASSWORD},
        follow_redirects=False,
    )
    assert post.status_code in (301, 302)

    response = client.get("/")
    assert response.status_code == 200


def test_login_with_wrong_password_returns_401(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    response = client.post("/login", data={"username": "admin", "password": "wrongpassword"})
    assert response.status_code == 401
    assert b"Invalid username or password" in response.data


def test_login_with_wrong_username_returns_401(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    response = client.post("/login", data={"username": "notadmin", "password": _TEST_PASSWORD})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Auth enabled - logout
# ---------------------------------------------------------------------------

def test_logout_clears_session(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    client.post("/login", data={"username": "admin", "password": _TEST_PASSWORD})

    # Confirm access is granted.
    assert client.get("/").status_code == 200

    # Log out and confirm access is revoked.
    client.post("/logout")
    response = client.get("/")
    assert response.status_code in (301, 302)
    assert "login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# Login next-URL redirect safety
# ---------------------------------------------------------------------------

def test_login_next_param_redirects_to_safe_path(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    post = client.post(
        "/login?next=/remote",
        data={"username": "admin", "password": _TEST_PASSWORD},
        follow_redirects=False,
    )
    assert post.status_code in (301, 302)
    assert post.headers["Location"].endswith("/remote")


def test_login_next_param_ignores_external_url(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True)
    post = client.post(
        "/login?next=https://evil.example.com",
        data={"username": "admin", "password": _TEST_PASSWORD},
        follow_redirects=False,
    )
    assert post.status_code in (301, 302)
    location = post.headers["Location"]
    assert "evil.example.com" not in location
    assert location.endswith("/")


# ---------------------------------------------------------------------------
# Must-change-password flow
# ---------------------------------------------------------------------------

def test_auth_must_change_password_default_is_false():
    from retrostation_player.config import DEFAULT_CONFIG
    assert DEFAULT_CONFIG["auth_must_change_password"] is False


def test_login_redirects_to_change_password_when_flag_set(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True, must_change_password=True)
    post = client.post(
        "/login",
        data={"username": "admin", "password": _TEST_PASSWORD},
        follow_redirects=False,
    )
    assert post.status_code in (301, 302)
    assert "change-password" in post.headers["Location"]


def test_change_password_page_renders(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True, must_change_password=True)
    client.post("/login", data={"username": "admin", "password": _TEST_PASSWORD})
    response = client.get("/change-password")
    assert response.status_code == 200
    assert b"Change Password" in response.data


def test_change_password_redirects_to_index_on_success(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True, must_change_password=True)
    client.post("/login", data={"username": "admin", "password": _TEST_PASSWORD})
    post = client.post(
        "/change-password",
        data={"new_password": "newpass456", "confirm_password": "newpass456"},
        follow_redirects=False,
    )
    assert post.status_code in (301, 302)
    assert post.headers["Location"].endswith("/")


def test_change_password_rejects_mismatched_passwords(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True, must_change_password=True)
    client.post("/login", data={"username": "admin", "password": _TEST_PASSWORD})
    response = client.post(
        "/change-password",
        data={"new_password": "newpass456", "confirm_password": "different"},
    )
    assert response.status_code == 400
    assert b"Passwords do not match" in response.data


def test_change_password_rejects_empty_password(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True, must_change_password=True)
    client.post("/login", data={"username": "admin", "password": _TEST_PASSWORD})
    response = client.post(
        "/change-password",
        data={"new_password": "", "confirm_password": ""},
    )
    assert response.status_code == 400
    assert b"cannot be empty" in response.data


def test_change_password_unauthenticated_redirects_to_login(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True, must_change_password=True)
    response = client.get("/change-password", follow_redirects=False)
    assert response.status_code in (301, 302)
    assert "login" in response.headers["Location"]


def test_login_without_must_change_password_goes_to_index(monkeypatch, tmp_path):
    client = _make_app(monkeypatch, tmp_path, auth_enabled=True, must_change_password=False)
    post = client.post(
        "/login",
        data={"username": "admin", "password": _TEST_PASSWORD},
        follow_redirects=False,
    )
    assert post.status_code in (301, 302)
    assert "change-password" not in post.headers["Location"]
    assert post.headers["Location"].endswith("/")
