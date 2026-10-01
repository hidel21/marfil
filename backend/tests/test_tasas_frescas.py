"""La app pone al dia las tasas sola, sin depender del cron."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.services import tasas_frescas

pytestmark = pytest.mark.usefixtures("engine")


@pytest.fixture
def llamadas(monkeypatch):
    registro: list[str] = []
    import app.jobs.operativos as operativos

    monkeypatch.setattr(
        operativos, "backfill_tasas", lambda desde: registro.append(f"backfill {desde}")
    )
    monkeypatch.setattr(operativos, "snapshot_tasa", lambda: registro.append("snapshot"))
    monkeypatch.setattr(
        tasas_frescas,
        "obtener_settings",
        lambda: SimpleNamespace(tasas_automaticas=True, zona_horaria="America/Caracas"),
    )
    monkeypatch.setattr(tasas_frescas, "_ultimo_intento", 0.0)
    # Un "hoy" lejano: ninguna tasa de la base de test puede ser de ese dia.
    monkeypatch.setattr(tasas_frescas, "_hoy", lambda zona: date(2099, 1, 1))
    return registro


def test_si_la_tasa_es_vieja_se_trae_lo_que_falta(llamadas):
    # La base de test no tiene tasas de hoy.
    assert tasas_frescas.asegurar() is True
    assert llamadas[-1] == "snapshot" and llamadas[0].startswith("backfill")


def test_no_reintenta_dentro_de_la_misma_hora(llamadas):
    tasas_frescas.asegurar()
    antes = len(llamadas)
    assert tasas_frescas.asegurar() is False
    assert len(llamadas) == antes


def test_apagado_no_hace_nada(monkeypatch, llamadas):
    monkeypatch.setattr(
        tasas_frescas,
        "obtener_settings",
        lambda: SimpleNamespace(tasas_automaticas=False, zona_horaria="America/Caracas"),
    )
    assert tasas_frescas.asegurar() is False
    assert llamadas == []
