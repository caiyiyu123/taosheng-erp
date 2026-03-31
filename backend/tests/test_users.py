from app.models.user import User
from app.utils.security import hash_password


def _get_admin_token(client, db):
    user = User(username="admin", password_hash=hash_password("admin123"), role="admin", is_active=True)
    db.add(user)
    db.commit()
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_users(client, db):
    token = _get_admin_token(client, db)
    resp = client.get("/api/users", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_create_user(client, db):
    token = _get_admin_token(client, db)
    resp = client.post("/api/users", json={
        "username": "operator1", "password": "pass123", "role": "operator"
    }, headers=_auth(token))
    assert resp.status_code == 201
    assert resp.json()["username"] == "operator1"


def test_create_duplicate_user(client, db):
    token = _get_admin_token(client, db)
    client.post("/api/users", json={"username": "op1", "password": "pass", "role": "operator"}, headers=_auth(token))
    resp = client.post("/api/users", json={"username": "op1", "password": "pass", "role": "operator"}, headers=_auth(token))
    assert resp.status_code == 400


def test_update_user(client, db):
    token = _get_admin_token(client, db)
    create = client.post("/api/users", json={"username": "op1", "password": "pass", "role": "operator"}, headers=_auth(token))
    user_id = create.json()["id"]
    resp = client.put(f"/api/users/{user_id}", json={"role": "viewer"}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"


def test_delete_user(client, db):
    token = _get_admin_token(client, db)
    create = client.post("/api/users", json={"username": "op1", "password": "pass", "role": "operator"}, headers=_auth(token))
    user_id = create.json()["id"]
    resp = client.delete(f"/api/users/{user_id}", headers=_auth(token))
    assert resp.status_code == 200


def test_non_admin_cannot_manage_users(client, db):
    token = _get_admin_token(client, db)
    client.post("/api/users", json={"username": "viewer1", "password": "pass", "role": "viewer"}, headers=_auth(token))
    viewer_login = client.post("/api/auth/login", data={"username": "viewer1", "password": "pass"})
    viewer_token = viewer_login.json()["access_token"]
    resp = client.get("/api/users", headers=_auth(viewer_token))
    assert resp.status_code == 403
