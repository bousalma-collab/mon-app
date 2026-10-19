"""Tests de l'authentification locale (hachage des codes et comptes SQLite)."""

from __future__ import annotations

import pytest

import auth
import db


# ---------------------------------------------------------------------------
# Fonctions pures de auth.py
# ---------------------------------------------------------------------------
def test_hachage_non_reversible_et_verification():
    sel = auth.generer_sel()
    empreinte = auth.hacher_code("secret123", sel)
    assert empreinte != "secret123"
    assert len(empreinte) == 64  # SHA-256 en hexadecimal
    assert auth.verifier_code("secret123", sel, empreinte)
    assert not auth.verifier_code("secret124", sel, empreinte)


def test_deux_comptes_avec_le_meme_code_ont_des_empreintes_differentes():
    premier = auth.hacher_code("secret123", auth.generer_sel())
    second = auth.hacher_code("secret123", auth.generer_sel())
    assert premier != second


def test_verification_avec_champs_vides():
    assert not auth.verifier_code("", "00" * 16, "abc")
    assert not auth.verifier_code("secret", "", "abc")
    assert not auth.verifier_code("secret", "00" * 16, "")


def test_normalisation_du_nom_utilisateur():
    assert auth.normaliser_username("  Admin ") == "admin"
    assert auth.normaliser_username("salma.b") == "salma.b"


@pytest.mark.parametrize("nom", ["", "   ", "a b", "é" * 3, "a" * 40, "-abc"])
def test_noms_utilisateurs_refuses(nom):
    with pytest.raises(ValueError):
        auth.normaliser_username(nom)


def test_validation_du_code():
    assert auth.valider_code("abc123") == "abc123"
    with pytest.raises(ValueError):
        auth.valider_code("abc")
    with pytest.raises(ValueError):
        auth.valider_code(" abc123")
    with pytest.raises(ValueError):
        auth.valider_code("")


def test_libelle_role():
    assert auth.libelle_role("admin") == "Administrateur"
    assert auth.libelle_role("lecteur") == "Consultation"
    assert auth.libelle_role("inconnu") == "Consultation"


# ---------------------------------------------------------------------------
# Comptes stockes en base
# ---------------------------------------------------------------------------
@pytest.fixture()
def connexion(tmp_path):
    conn = db.connect(tmp_path / "auth_test.db")
    db.init_db(conn)
    yield conn
    conn.close()


def test_comptes_par_defaut_crees(connexion):
    noms = {compte["username"] for compte in db.list_users(connexion)}
    assert {"admin", "demo"} <= noms


def test_comptes_par_defaut_crees_une_seule_fois(connexion):
    avant = len(db.list_users(connexion))
    assert db.ensure_default_users(connexion) == 0
    assert len(db.list_users(connexion)) == avant


def test_authentification_valide(connexion):
    utilisateur = db.authenticate(connexion, "admin", "cashflow2026")
    assert utilisateur is not None
    assert utilisateur["username"] == "admin"
    assert utilisateur["role"] == "admin"


def test_authentification_refusee(connexion):
    assert db.authenticate(connexion, "admin", "mauvais-code") is None
    assert db.authenticate(connexion, "inconnu", "cashflow2026") is None
    assert db.authenticate(connexion, "", "") is None


def test_nom_utilisateur_insensible_a_la_casse(connexion):
    assert db.authenticate(connexion, "  ADMIN ", "cashflow2026") is not None


def test_compte_desactive_refuse(connexion):
    demo = db.get_user(connexion, "demo")
    db.set_user_active(connexion, demo["id"], False)
    assert db.authenticate(connexion, "demo", "demo2026") is None
    db.set_user_active(connexion, demo["id"], True)
    assert db.authenticate(connexion, "demo", "demo2026") is not None


def test_creation_utilisateur_et_refus_du_doublon(connexion):
    db.create_user(connexion, "salma", "salma2026", "Salma B.", "lecteur")
    assert db.authenticate(connexion, "salma", "salma2026") is not None
    with pytest.raises(ValueError):
        db.create_user(connexion, "SALMA", "autre2026", "", "lecteur")


def test_changement_de_code(connexion):
    demo = db.get_user(connexion, "demo")
    db.update_user_code(connexion, demo["id"], "nouveau2026")
    assert db.authenticate(connexion, "demo", "demo2026") is None
    assert db.authenticate(connexion, "demo", "nouveau2026") is not None


def test_dernier_administrateur_protege(connexion):
    admin = db.get_user(connexion, "admin")
    with pytest.raises(ValueError):
        db.delete_user(connexion, admin["id"])
    with pytest.raises(ValueError):
        db.set_user_active(connexion, admin["id"], False)


def test_suppression_utilisateur(connexion):
    identifiant = db.create_user(connexion, "temporaire", "temp2026", "", "lecteur")
    db.delete_user(connexion, identifiant)
    assert db.get_user(connexion, "temporaire") is None


def test_code_jamais_stocke_en_clair(connexion):
    ligne = connexion.execute(
        "SELECT code_hash, salt FROM users WHERE username = 'admin'"
    ).fetchone()
    assert "cashflow2026" not in ligne["code_hash"]
    assert len(ligne["salt"]) == auth.LONGUEUR_SEL * 2
