"""Tests des calculs financiers de CashFlow AI (exemples numeriques explicites)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

import db
import demo_data
import finance
import io_utils

AUJOURDHUI = date(2026, 6, 15)


# ---------------------------------------------------------------------------
# Outils de test
# ---------------------------------------------------------------------------
def reglages(solde=100000.0, seuil=5000.0, devise="MAD") -> dict:
    return {
        "id": 1,
        "company_name": "Test SARL",
        "currency": devise,
        "opening_cash": solde,
        "opening_cash_date": AUJOURDHUI - timedelta(days=365),
        "min_cash_threshold": seuil,
        "demo_mode": 0,
    }


def tx(
    identifiant,
    jour,
    montant,
    tx_type="Encaissement",
    statut="Réalisé",
    date_prevue=None,
    categorie="Ventes",
    facture_id=None,
) -> dict:
    return {
        "id": identifiant,
        "date": jour,
        "type": tx_type,
        "category": categorie,
        "description": f"opération {identifiant}",
        "amount": float(montant),
        "status": statut,
        "expected_date": date_prevue,
        "party": "Tiers",
        "reference": f"REF-{identifiant}",
        "invoice_id": facture_id,
    }


def facture(
    identifiant,
    total,
    paye=0.0,
    inv_type="Client",
    echeance=None,
    numero=None,
) -> dict:
    echeance = echeance or AUJOURDHUI + timedelta(days=10)
    return {
        "id": identifiant,
        "number": numero or f"FA-2026-{identifiant:04d}",
        "type": inv_type,
        "party": "Client Test",
        "issue_date": AUJOURDHUI - timedelta(days=20),
        "due_date": echeance,
        "total": float(total),
        "paid": float(paye),
        "status": "Ouverte",
        "notes": "",
    }


@pytest.fixture()
def conn():
    connexion = db.connect(":memory:")
    db.init_db(connexion)
    yield connexion
    connexion.close()


# ---------------------------------------------------------------------------
# 1. Tresorerie reelle
# ---------------------------------------------------------------------------
def test_tresorerie_reelle():
    parametres = reglages(solde=100_000)
    transactions = [
        tx(1, AUJOURDHUI, 50_000, "Encaissement"),
        tx(2, AUJOURDHUI, 30_000, "Décaissement"),
    ]
    assert finance.actual_cash(parametres, transactions) == 120_000.0


def test_tresorerie_reelle_soustraction_des_decaissements():
    parametres = reglages(solde=10_000)
    transactions = [tx(1, AUJOURDHUI, 2_500, "Décaissement")]
    assert finance.actual_cash(parametres, transactions) == 7_500.0


# ---------------------------------------------------------------------------
# 2. Flux net
# ---------------------------------------------------------------------------
def test_flux_net_du_mois():
    transactions = [
        tx(1, date(2026, 6, 10), 50_000, "Encaissement"),
        tx(2, date(2026, 6, 20), 20_000, "Décaissement"),
        tx(3, date(2026, 5, 28), 99_000, "Encaissement"),  # hors periode
    ]
    assert finance.net_cash_flow(transactions, date(2026, 6, 1), date(2026, 6, 30)) == 30_000.0


# ---------------------------------------------------------------------------
# 3. Exclusion des transactions prevues
# ---------------------------------------------------------------------------
def test_transactions_prevues_exclues_de_la_tresorerie_reelle():
    parametres = reglages(solde=10_000)
    transactions = [
        tx(1, AUJOURDHUI, 5_000, "Encaissement", "Réalisé"),
        tx(2, AUJOURDHUI, 999_999, "Encaissement", "Prévu"),
        tx(3, AUJOURDHUI, 999_999, "Décaissement", "En retard"),
    ]
    assert finance.actual_cash(parametres, transactions) == 15_000.0
    assert finance.cash_totals(transactions)["net"] == 5_000.0


# ---------------------------------------------------------------------------
# 4. Solde restant d'une facture
# ---------------------------------------------------------------------------
def test_solde_restant_facture():
    assert finance.invoice_remaining(facture(1, 10_000, 4_000)) == 6_000.0
    assert finance.invoice_remaining(facture(2, 10_000, 10_000)) == 0.0
    # Un trop-percu ne doit jamais produire un solde negatif
    assert finance.invoice_remaining(facture(3, 10_000, 12_000)) == 0.0


# ---------------------------------------------------------------------------
# 5. Paiement partiel (base de donnees reelle)
# ---------------------------------------------------------------------------
def test_paiement_partiel(conn):
    identifiant = db.add_invoice(
        conn,
        {
            "number": "FA-2026-0001",
            "type": "Client",
            "party": "Client Partiel",
            "issue_date": date.today() - timedelta(days=10),
            "due_date": date.today() + timedelta(days=20),
            "total": 10_000,
            "paid": 0,
        },
    )
    parametres = db.get_settings(conn)
    avant = finance.actual_cash(parametres, db.list_transactions(conn))

    resultat = db.record_payment(conn, identifiant, 4_000, date.today(), "Acompte")

    facture_maj = db.get_invoice(conn, identifiant)
    transactions = db.list_transactions(conn)
    assert facture_maj["paid"] == 4_000.0
    assert facture_maj["remaining"] == 6_000.0
    assert facture_maj["status"] == "Partiellement payée"
    assert len(transactions) == 1
    assert transactions[0]["amount"] == 4_000.0
    assert transactions[0]["type"] == "Encaissement"
    assert transactions[0]["status"] == "Réalisé"
    assert transactions[0]["invoice_id"] == identifiant
    assert finance.actual_cash(parametres, transactions) == avant + 4_000.0
    assert resultat["remaining"] == 6_000.0


# ---------------------------------------------------------------------------
# 6. Paiement total
# ---------------------------------------------------------------------------
def test_paiement_total(conn):
    identifiant = db.add_invoice(
        conn,
        {
            "number": "FF-2026-0001",
            "type": "Fournisseur",
            "party": "Fournisseur Test",
            "issue_date": date.today() - timedelta(days=5),
            "due_date": date.today() + timedelta(days=5),
            "total": 7_500,
            "paid": 0,
        },
    )
    db.record_payment(conn, identifiant, 2_500, date.today() - timedelta(days=1))
    resultat = db.record_payment(conn, identifiant, 5_000, date.today())

    facture_maj = db.get_invoice(conn, identifiant)
    assert facture_maj["paid"] == 7_500.0
    assert facture_maj["remaining"] == 0.0
    assert facture_maj["status"] == "Payée"
    assert resultat["new_status"] == "Payée"
    transactions = db.list_transactions(conn)
    assert len(transactions) == 2
    assert all(t["type"] == "Décaissement" for t in transactions)
    parametres = db.get_settings(conn)
    assert finance.actual_cash(parametres, transactions) == -7_500.0


# ---------------------------------------------------------------------------
# 7. Detection des factures en retard
# ---------------------------------------------------------------------------
def test_detection_facture_en_retard():
    en_retard = facture(1, 5_000, 0, echeance=AUJOURDHUI - timedelta(days=12))
    a_echeance = facture(2, 5_000, 0, echeance=AUJOURDHUI + timedelta(days=3))
    soldee = facture(3, 5_000, 5_000, echeance=AUJOURDHUI - timedelta(days=30))
    listes = [en_retard, a_echeance, soldee]

    assert finance.compute_invoice_status(en_retard, AUJOURDHUI) == "En retard"
    assert finance.compute_invoice_status(a_echeance, AUJOURDHUI) == "Ouverte"
    assert finance.compute_invoice_status(soldee, AUJOURDHUI) == "Payée"
    assert finance.overdue_days(en_retard, AUJOURDHUI) == 12
    assert [f["id"] for f in finance.overdue_invoices(listes, AUJOURDHUI)] == [1]


# ---------------------------------------------------------------------------
# 8. Prevision journaliere
# ---------------------------------------------------------------------------
def test_prevision_journaliere():
    parametres = reglages(solde=10_000, seuil=5_000)
    transactions = [
        tx(1, AUJOURDHUI + timedelta(days=3), 2_000, "Encaissement", "Prévu",
           AUJOURDHUI + timedelta(days=3)),
        tx(2, AUJOURDHUI + timedelta(days=5), 1_000, "Décaissement", "Prévu",
           AUJOURDHUI + timedelta(days=5)),
    ]
    factures = [facture(1, 4_000, 0, echeance=AUJOURDHUI + timedelta(days=2))]

    prevision = finance.build_forecast(parametres, transactions, factures, AUJOURDHUI, 10)
    jours = prevision["days"]

    assert len(jours) == 11  # de aujourd'hui a J+10 inclus
    assert jours[0]["closing"] == 10_000.0
    assert jours[1]["closing"] == 10_000.0
    assert jours[2]["closing"] == 14_000.0  # + facture 4 000
    assert jours[3]["closing"] == 16_000.0  # + encaissement prevu 2 000
    assert jours[4]["closing"] == 16_000.0
    assert jours[5]["closing"] == 15_000.0  # - decaissement prevu 1 000
    assert jours[10]["closing"] == 15_000.0
    assert prevision["final_cash"] == 15_000.0
    assert prevision["min_cash"] == 10_000.0
    assert prevision["days_below_threshold"] == 0
    assert prevision["first_negative_date"] is None
    assert prevision["opening_cash"] == 10_000.0


# ---------------------------------------------------------------------------
# 9. Alerte de tresorerie negative
# ---------------------------------------------------------------------------
def test_alerte_tresorerie_negative():
    parametres = reglages(solde=1_000, seuil=2_000)
    transactions = [tx(1, AUJOURDHUI, 5_000, "Décaissement", "Prévu", AUJOURDHUI + timedelta(days=2))]
    factures: list[dict] = []

    prevision = finance.build_forecast(parametres, transactions, factures, AUJOURDHUI, 30)
    assert prevision["first_negative_date"] == AUJOURDHUI + timedelta(days=2)
    assert prevision["min_cash"] == -4_000.0

    alertes = finance.build_alerts(parametres, transactions, factures, prevision, AUJOURDHUI)
    titres = [a["title"] for a in alertes]
    niveaux = {a["level"] for a in alertes}
    assert "Trésorerie prévisionnelle négative" in titres
    assert "danger" in niveaux
    assert any("seuil" in titre.lower() for titre in titres)

    risque = finance.liquidity_risk_score(parametres, transactions, factures, prevision)
    assert risque["score"] >= 70
    assert risque["level"] == "danger"


# ---------------------------------------------------------------------------
# 10. Simulation : retard de paiement client
# ---------------------------------------------------------------------------
def test_simulation_retard_de_paiement():
    parametres = reglages(solde=10_000, seuil=0)
    transactions: list[dict] = []
    factures = [facture(1, 5_000, 0, echeance=AUJOURDHUI + timedelta(days=5))]

    base = finance.build_forecast(parametres, transactions, factures, AUJOURDHUI, 30)
    assert base["days"][5]["closing"] == 15_000.0
    assert base["final_cash"] == 15_000.0

    cible = [i for i in base["items"] if i["direction"] == "in"][0]
    nouvelles_tx, nouvelles_factures = finance.delay_item(transactions, factures, cible, 20)
    scenario = finance.build_forecast(
        parametres, nouvelles_tx, nouvelles_factures, AUJOURDHUI, 30
    )

    assert scenario["days"][10]["closing"] == 10_000.0  # le reglement n'est pas encore arrive
    assert base["days"][10]["closing"] - scenario["days"][10]["closing"] == 5_000.0
    assert scenario["final_cash"] == base["final_cash"] == 15_000.0  # arrive a J+25
    # Les donnees d'origine ne sont pas modifiees
    assert factures[0]["due_date"] == AUJOURDHUI + timedelta(days=5)

    comparaison = finance.compare_forecasts(base, scenario)
    assert comparaison["final_delta"] == 0.0


def test_simulation_retard_cree_une_tension():
    parametres = reglages(solde=3_000, seuil=5_000)
    factures = [facture(1, 20_000, 0, echeance=AUJOURDHUI + timedelta(days=3))]
    transactions = [
        tx(1, AUJOURDHUI + timedelta(days=4), 10_000, "Décaissement", "Prévu",
           AUJOURDHUI + timedelta(days=4))
    ]
    base = finance.build_forecast(parametres, transactions, factures, AUJOURDHUI, 30)
    cible = [i for i in base["items"] if i["direction"] == "in"][0]
    tx_retard, factures_retard = finance.delay_item(transactions, factures, cible, 15)
    scenario = finance.build_forecast(
        parametres, tx_retard, factures_retard, AUJOURDHUI, 30
    )
    assert base["first_negative_date"] is None
    assert scenario["first_negative_date"] == AUJOURDHUI + timedelta(days=4)


# ---------------------------------------------------------------------------
# 11. Simulation : hausse des depenses
# ---------------------------------------------------------------------------
def test_simulation_hausse_des_depenses():
    parametres = reglages(solde=10_000, seuil=0)
    transactions = [
        tx(1, AUJOURDHUI + timedelta(days=3), 2_000, "Décaissement", "Prévu",
           AUJOURDHUI + timedelta(days=3)),
        tx(2, AUJOURDHUI - timedelta(days=2), 4_000, "Décaissement", "Réalisé"),
    ]
    transactions_augmentees = finance.scale_planned_expenses(transactions, 10)

    # Seules les sorties PREVUES augmentent (2 000 -> 2 200)
    assert transactions_augmentees[0]["amount"] == 2_200.0
    assert transactions_augmentees[1]["amount"] == 4_000.0

    base = finance.build_forecast(parametres, transactions, [], AUJOURDHUI, 10)
    scenario = finance.build_forecast(parametres, transactions_augmentees, [], AUJOURDHUI, 10)
    assert base["final_cash"] == 4_000.0  # 10 000 - 4 000 realise - 2 000 prevu
    assert scenario["final_cash"] == 3_800.0
    assert finance.compare_forecasts(base, scenario)["final_delta"] == -200.0


def test_simulation_depense_exceptionnelle():
    parametres = reglages(solde=10_000, seuil=0)
    base = finance.build_forecast(parametres, [], [], AUJOURDHUI, 30)
    avec_depense = finance.add_planned_expense(
        [], AUJOURDHUI + timedelta(days=12), 6_000, "Achat machine"
    )
    scenario = finance.build_forecast(parametres, avec_depense, [], AUJOURDHUI, 30)
    assert base["final_cash"] == 10_000.0
    assert scenario["final_cash"] == 4_000.0
    assert scenario["min_cash"] == 4_000.0


# ---------------------------------------------------------------------------
# 12. Refus du trop-percu
# ---------------------------------------------------------------------------
def test_refus_surpaiement(conn):
    identifiant = db.add_invoice(
        conn,
        {
            "number": "FA-2026-0007",
            "type": "Client",
            "party": "Client Surpaiement",
            "issue_date": date.today(),
            "due_date": date.today() + timedelta(days=15),
            "total": 10_000,
            "paid": 0,
        },
    )
    with pytest.raises(ValueError) as erreur:
        db.record_payment(conn, identifiant, 10_001, date.today())
    assert "solde restant" in str(erreur.value).lower() or "surpaiement" in str(erreur.value).lower()

    facture_apres = db.get_invoice(conn, identifiant)
    assert facture_apres["paid"] == 0.0
    assert facture_apres["remaining"] == 10_000.0
    assert db.list_transactions(conn) == []
    assert db.list_payments(conn) == []


# ---------------------------------------------------------------------------
# 13. Refus du paiement en doublon
# ---------------------------------------------------------------------------
def test_refus_paiement_en_doublon(conn):
    identifiant = db.add_invoice(
        conn,
        {
            "number": "FF-2026-0009",
            "type": "Fournisseur",
            "party": "Fournisseur Doublon",
            "issue_date": date.today(),
            "due_date": date.today() + timedelta(days=10),
            "total": 20_000,
            "paid": 0,
        },
    )
    db.record_payment(conn, identifiant, 3_000, date.today())
    with pytest.raises(ValueError) as erreur:
        db.record_payment(conn, identifiant, 3_000, date.today())
    assert "doublon" in str(erreur.value).lower()

    assert len(db.list_payments(conn)) == 1
    assert len(db.list_transactions(conn)) == 1
    assert db.get_invoice(conn, identifiant)["paid"] == 3_000.0

    # Un montant different le meme jour reste autorise
    db.record_payment(conn, identifiant, 2_000, date.today())
    assert db.get_invoice(conn, identifiant)["paid"] == 5_000.0
    assert len(db.list_transactions(conn)) == 2


# ---------------------------------------------------------------------------
# 14. Pas de double comptage facture / transaction prevue
# ---------------------------------------------------------------------------
def test_pas_de_double_comptage_facture_et_transaction_prevue():
    parametres = reglages(solde=5_000, seuil=0)
    factures = [facture(42, 5_000, 0, echeance=AUJOURDHUI + timedelta(days=4))]
    transactions = [
        tx(1, AUJOURDHUI + timedelta(days=10), 5_000, "Encaissement", "Prévu",
           AUJOURDHUI + timedelta(days=10), facture_id=42)
    ]
    prevision = finance.build_forecast(parametres, transactions, factures, AUJOURDHUI, 30)

    items = prevision["items"]
    assert len(items) == 1
    assert items[0]["source"] == "transaction"
    assert items[0]["date"] == AUJOURDHUI + timedelta(days=10)
    assert prevision["total_inflows"] == 5_000.0
    assert prevision["final_cash"] == 10_000.0

    # Sans lien, la facture est utilisee une seule fois elle aussi
    prevision_sans_lien = finance.build_forecast(
        parametres, [], factures, AUJOURDHUI, 30
    )
    assert len(prevision_sans_lien["items"]) == 1
    assert prevision_sans_lien["items"][0]["source"] == "invoice"
    assert prevision_sans_lien["final_cash"] == 10_000.0


# ---------------------------------------------------------------------------
# Regles annexes : saisie, statuts, mise en coherence
# ---------------------------------------------------------------------------
def test_validation_des_saisies(conn):
    with pytest.raises(ValueError):
        db.validate_transaction({"date": "2026-06-15", "type": "Entrée", "amount": 100})
    with pytest.raises(ValueError):
        db.validate_transaction({"date": "2026-06-15", "type": "Encaissement", "amount": -5})
    with pytest.raises(ValueError):
        db.validate_transaction({"date": "pas une date", "type": "Encaissement", "amount": 5})
    with pytest.raises(ValueError):
        db.validate_invoice(
            {
                "number": "FA-1",
                "type": "Client",
                "party": "P",
                "issue_date": "2026-06-15",
                "due_date": "2026-06-01",
                "total": 100,
            }
        )
    valide = db.validate_transaction(
        {"date": "15/06/2026", "type": "Encaissement", "amount": "1 250,50", "status": "Réalisé"}
    )
    assert valide["date"] == date(2026, 6, 15)
    assert valide["amount"] == 1250.50


def test_statut_en_retard_automatique(conn):
    db.add_transaction(
        conn,
        {
            "date": date.today() - timedelta(days=10),
            "type": "Décaissement",
            "category": "Achats",
            "amount": 1_000,
            "status": "Prévu",
            "expected_date": date.today() - timedelta(days=3),
        },
    )
    assert db.list_transactions(conn)[0]["status"] == "Prévu"
    db.refresh_transaction_statuses(conn, date.today())
    assert db.list_transactions(conn)[0]["status"] == "En retard"


def test_suppression_transaction_liee_annule_le_paiement(conn):
    identifiant = db.add_invoice(
        conn,
        {
            "number": "FA-2026-0020",
            "type": "Client",
            "party": "Client Suppression",
            "issue_date": date.today(),
            "due_date": date.today() + timedelta(days=10),
            "total": 8_000,
            "paid": 0,
        },
    )
    db.record_payment(conn, identifiant, 8_000, date.today())
    transaction = db.list_transactions(conn)[0]
    info = db.delete_transaction(conn, transaction["id"])

    assert info["invoice_updated"] is True
    assert db.get_invoice(conn, identifiant)["paid"] == 0.0
    assert db.get_invoice(conn, identifiant)["status"] == "Ouverte"
    assert db.list_payments(conn) == []


def test_parametres_valides(conn):
    db.update_settings(conn, company_name="Ma PME", opening_cash=250_000, min_cash_threshold=50_000)
    parametres = db.get_settings(conn)
    assert parametres["company_name"] == "Ma PME"
    assert parametres["opening_cash"] == 250_000.0
    assert parametres["min_cash_threshold"] == 50_000.0
    with pytest.raises(ValueError):
        db.update_settings(conn, company_name="   ")
    with pytest.raises(ValueError):
        db.update_settings(conn, min_cash_threshold=-10)


# ---------------------------------------------------------------------------
# Jeu de demonstration et exports
# ---------------------------------------------------------------------------
def test_jeu_de_demonstration(conn):
    resume = demo_data.load_demo_data(conn, AUJOURDHUI)
    parametres = db.get_settings(conn)
    transactions = db.list_transactions(conn)
    factures = db.list_invoices(conn)

    assert parametres["demo_mode"] == 1
    assert parametres["company_name"] == "Atlas Distribution SARL"
    assert resume["completed_transactions"] >= 10
    assert resume["client_invoices"] >= 5
    assert resume["supplier_invoices"] >= 5
    assert resume["payments"] >= 3

    # La tresorerie reelle correspond a la cible et exclut les operations prevues
    assert finance.actual_cash(parametres, transactions) == pytest.approx(
        demo_data.TARGET_CASH_TODAY, abs=0.01
    )
    reelles = [t for t in transactions if finance.is_actual(t)]
    prevues = [t for t in transactions if not finance.is_actual(t)]
    assert len(reelles) >= 10
    assert len(prevues) >= 5
    assert finance.actual_cash(parametres, prevues) == parametres["opening_cash"]

    # Facture client en retard presente
    retards = finance.overdue_invoices(factures, AUJOURDHUI, inv_type="Client")
    assert len(retards) >= 1

    # Le scenario de tension previsionnelle est visible
    prevision = finance.build_forecast(parametres, transactions, factures, AUJOURDHUI, 30, 7)
    assert prevision["min_cash"] < parametres["min_cash_threshold"]
    alertes = finance.build_alerts(parametres, transactions, factures, prevision, AUJOURDHUI)
    assert len(alertes) >= 3

    # Les factures non soldees sans transaction liee alimentent la prevision
    identifiants_lies = {
        t["invoice_id"] for t in prevues if t.get("invoice_id")
    }
    for item in prevision["items"]:
        if item["source"] == "invoice":
            assert item["source_id"] not in identifiants_lies


def test_demonstration_ne_duplique_pas_les_donnees(conn):
    demo_data.load_demo_data(conn, AUJOURDHUI)
    premier = db.database_stats(conn)
    demo_data.load_demo_data(conn, AUJOURDHUI)
    second = db.database_stats(conn)
    assert premier["transactions"] == second["transactions"]
    assert premier["invoices"] == second["invoices"]


def test_simulations_ne_modifient_pas_les_donnees(conn):
    demo_data.load_demo_data(conn, AUJOURDHUI)
    avant = db.database_stats(conn)
    transactions = db.list_transactions(conn)
    factures = db.list_invoices(conn)
    parametres = db.get_settings(conn)
    somme_avant = sum(finance.to_decimal(t["amount"]) for t in transactions)

    base = finance.build_forecast(parametres, transactions, factures, AUJOURDHUI, 30, 7)
    cible = [i for i in base["items"] if i["direction"] == "in"][0]
    finance.delay_item(transactions, factures, cible, 25)
    finance.scale_planned_expenses(transactions, 30)
    finance.add_planned_expense(transactions, AUJOURDHUI, 500_000)

    apres = db.database_stats(conn)
    somme_apres = sum(
        finance.to_decimal(t["amount"]) for t in db.list_transactions(conn)
    )
    assert avant == apres
    assert somme_avant == somme_apres


def test_exports_csv_et_excel(conn):
    demo_data.load_demo_data(conn, AUJOURDHUI)
    transactions = db.list_transactions(conn)
    factures = db.list_invoices(conn)
    df = io_utils.transactions_dataframe(transactions)

    csv = io_utils.to_csv_bytes(df)
    assert b";" in csv
    assert "Montant (MAD)" in csv.decode("utf-8-sig")

    excel = io_utils.to_excel_bytes(
        {"Transactions": df, "Factures": io_utils.invoices_dataframe(factures, AUJOURDHUI)}
    )
    assert excel[:2] == b"PK"
    assert len(excel) > 5_000


def test_import_transactions_avec_lignes_invalides():
    contenu = (
        "date;type;categorie;description;montant;statut;tiers\n"
        "15/06/2026;Encaissement;Ventes;Vente A;1500,50;Réalisé;Client A\n"
        "16/06/2026;Décaissement;Achats;Achat B;800;Prévu;Fournisseur B\n"
        "date invalide;Décaissement;Achats;Ligne cassée;100;Prévu;Fournisseur C\n"
        "17/06/2026;Décaissement;Achats;Montant négatif;-50;Prévu;Fournisseur D\n"
    )
    lignes, erreurs = io_utils.lire_fichier_transactions(contenu.encode("utf-8"), "test.csv")
    assert len(lignes) == 2
    assert len(erreurs) == 2
    assert lignes[0]["amount"] == 1500.50
    assert lignes[0]["type"] == "Encaissement"
    assert lignes[1]["date"] == date(2026, 6, 16)
    assert "Ligne 4" in erreurs[0]


def test_series_pour_graphiques(conn):
    demo_data.load_demo_data(conn, AUJOURDHUI)
    parametres = db.get_settings(conn)
    transactions = db.list_transactions(conn)

    serie = finance.cash_balance_series(
        parametres, transactions, AUJOURDHUI - timedelta(days=30), AUJOURDHUI
    )
    assert len(serie) == 31
    assert finance.money(serie[-1]["balance"]) == finance.actual_cash(parametres, transactions)

    mois = finance.monthly_cash_series(transactions, AUJOURDHUI, 6)
    assert len(mois) == 6
    assert all(m["inflows"] >= 0 and m["outflows"] >= 0 for m in mois)
