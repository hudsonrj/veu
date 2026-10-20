"""P0 — plano de controle autenticado (veuajustes)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VEU_AUTH_PASSWORD", "test-pass-veu-p0")
    monkeypatch.setenv("VEU_AUTH_SECRET", "test-signing-secret-32bytes!!")
    monkeypatch.setenv("VEU_AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("VEU_AUTH_ORIGINS", "https://veu.ch8ai.com.br,http://testserver")
    # evita carregar runtime pesado se possível — ainda importa api
    from veu import auth as veu_auth

    # limpa cache efêmero
    if hasattr(veu_auth._signing_secret, "_ephemeral"):
        delattr(veu_auth._signing_secret, "_ephemeral")

    from veu.api import app

    return TestClient(app, base_url="http://testserver")


def test_health_public(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_control_without_session_401(client: TestClient):
    r = client.get("/servers")
    assert r.status_code == 401
    r2 = client.get("/mission")
    assert r2.status_code == 401
    r3 = client.post("/chat", json={"message": "oi", "breath": "guided"})
    assert r3.status_code == 401


def test_control_with_session_200(client: TestClient):
    login = client.post("/auth/login", json={"password": "test-pass-veu-p0"})
    assert login.status_code == 200
    assert login.json().get("authenticated") is True
    assert "veu_session" in login.cookies

    r = client.get("/servers")
    assert r.status_code == 200
    body = r.json()
    # sem reveal: não vaza secret_env
    for s in body.get("servers") or []:
        assert "secret_env" not in s
        host = str(s.get("host") or "")
        assert "169.58" not in host or "***" in host or "…" in host or not host


def test_post_without_origin_403(client: TestClient):
    login = client.post("/auth/login", json={"password": "test-pass-veu-p0"})
    assert login.status_code == 200
    # TestClient normalmente não manda Origin — exige X-Véu-CSRF
    r = client.post(
        "/servers/fake/ssh",
        headers={},  # sem CSRF
    )
    # sem Origin e sem CSRF → 403
    assert r.status_code == 403

    r2 = client.post(
        "/servers/fake/ssh",
        headers={"X-Veu-CSRF": "1", "Origin": "https://evil.example"},
    )
    assert r2.status_code == 403

    r3 = client.post(
        "/servers/fake/ssh",
        headers={"X-Veu-CSRF": "1", "Origin": "https://veu.ch8ai.com.br"},
    )
    # autenticado + CSRF ok — pode 200 ou erro de negócio, nunca 401/403
    assert r3.status_code not in {401, 403}


def test_servers_mask_secret_env(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("VEU_DATA_ROOT", str(tmp_path))
    login = client.post("/auth/login", json={"password": "test-pass-veu-p0"})
    assert login.status_code == 200

    # cria servidor
    r = client.post(
        "/servers",
        json={
            "name": "lab",
            "host": "169.58.19.232",
            "port": 22,
            "username": "root",
            "password": "x" * 16,
        },
        headers={"X-Veu-CSRF": "1", "Origin": "https://veu.ch8ai.com.br"},
    )
    assert r.status_code == 200
    listed = client.get("/servers").json()
    assert listed["count"] >= 1
    row = listed["servers"][0]
    assert "secret_env" not in row
    assert row.get("host") != "169.58.19.232"
    assert "***" in str(row.get("host") or "") or "…" in str(row.get("host") or "")

    revealed = client.get("/servers?reveal=1").json()
    row2 = revealed["servers"][0]
    assert row2.get("host") == "169.58.19.232"
    assert "secret_env" in row2
