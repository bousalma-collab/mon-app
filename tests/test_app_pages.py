"""Test d'integration : l'application Streamlit demarre et toutes les pages s'affichent.

Ce test execute reellement app.py (via AppTest) sur une base SQLite temporaire,
d'abord vide puis remplie avec le jeu de demonstration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

PAGES = [
    "Tableau de bord",
    "Trésorerie",
    "Factures",
    "Prévisions",
    "Simulateur",
    "Assistant IA",
    "Rapports et paramètres",
]


@pytest.fixture()
def app_test(tmp_path, monkeypatch):
    import db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "cashflow_test.db")
    db.close_connection()

    from streamlit.testing.v1 import AppTest

    application = AppTest.from_file(str(RACINE / "app.py"), default_timeout=300)
    yield application
    db.close_connection()


def _verifier_pages(application) -> None:
    for page in PAGES:
        application.sidebar.radio[0].set_value(page).run()
        assert not application.exception, (
            f"Erreur sur la page {page} : "
            + " | ".join(str(e) for e in application.exception)
        )


def test_application_demarre_base_vide(app_test):
    app_test.run()
    assert not app_test.exception, [str(e) for e in app_test.exception]
    _verifier_pages(app_test)


def test_application_avec_donnees_de_demonstration(app_test):
    import db
    import demo_data

    connexion = db.get_connection()
    demo_data.load_demo_data(connexion)

    app_test.run()
    assert not app_test.exception, [str(e) for e in app_test.exception]
    _verifier_pages(app_test)

    # Le tableau de bord affiche des alertes reelles
    app_test.sidebar.radio[0].set_value("Tableau de bord").run()
    assert not app_test.exception
    texte = " ".join(bloc.value for bloc in app_test.markdown)
    assert "Trésorerie actuelle" in texte
    assert "Mode démonstration actif" in texte
