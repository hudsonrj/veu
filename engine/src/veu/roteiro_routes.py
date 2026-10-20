"""Rotas dos passos do roteiro (controle, integridade, billing, togo, about, projects)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from veu import about as veu_about
    from veu import togo as veu_togo

    @app.get("/about")
    def about() -> dict[str, Any]:
        return veu_about.about()

    # /control · /targets · /integrity · /data — registrados em api.py (9.8–9.9)

    # billing + projects CRUD vivem em api.py (7.3–7.6 / 10.x)

    @app.get("/togo/export")
    def togo_export() -> dict[str, Any]:
        return veu_togo.pack_export()

    @app.post("/togo/verify")
    def togo_verify(body: dict[str, Any]) -> dict[str, Any]:
        return veu_togo.verify_files(body.get("files") or {}, body.get("manifest") or {})

    @app.post("/togo/import/preview")
    def togo_import_preview(body: dict[str, Any]) -> dict[str, Any]:
        return veu_togo.import_preview(body.get("files") or {})

    @app.post("/togo/import/apply")
    def togo_import_apply(body: dict[str, Any]) -> dict[str, Any]:
        if not body.get("confirm"):
            return {
                "ok": False,
                "error": "confirmação obrigatória",
                "preview": veu_togo.import_preview(body.get("files") or {}),
            }
        return veu_togo.apply_import(body.get("files") or {})

    # Gate de pause: jobs.JobStore.enqueue consulta control.is_paused() nativamente

