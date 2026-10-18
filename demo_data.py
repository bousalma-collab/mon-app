"""Jeu de donnees de demonstration pour CashFlow AI.

Entreprise fictive : Atlas Distribution SARL (MAD).
Toutes les dates sont relatives a la date du jour afin que la demonstration
reste pertinente quelle que soit la date de la presentation.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

import db
import finance

TARGET_CASH_TODAY = 118_000.0  # tresorerie reelle visee a l'ouverture de la demo
SEUIL_DEMO = 150_000.0
SOLDE_HISTORIQUE = 320_000.0

CLIENTS = [
    "Marrakech Retail SARL",
    "Casablanca BTP SA",
    "Agadir Négoce SARL",
    "Fès Commerce SARL",
    "Tanger Import SARL",
    "Rabat Distribution SARL",
]

FOURNISSEURS = [
    "Sonasid Acier",
    "Lesieur Cristal",
    "Total Maroc",
    "Oulmès Boissons",
    "ElectroPlanet",
    "Marjane Pro",
]


def _jour(base: date, jour_du_mois: int) -> date:
    dernier = calendar.monthrange(base.year, base.month)[1]
    return base.replace(day=min(jour_du_mois, dernier))


def _historique(today: date) -> list[dict]:
    """Transactions realisees des 4 derniers mois (activite de l'entreprise)."""
    lignes: list[dict] = []
    limite = today - timedelta(days=1)
    mois_en_cours = today.replace(day=1)
    premier_mois = finance.add_months(mois_en_cours, -3)

    templates = [
        # (jour, type, categorie, description, montant)
        (3, "Encaissement", "Ventes", "Ventes comptoir — semaine 1", 68_000),
        (8, "Décaissement", "Achats", "Achat marchandises (grossiste)", 83_000),
        (10, "Encaissement", "Ventes", "Ventes comptoir — semaine 2", 68_000),
        (12, "Décaissement", "Transport", "Transport et logistique", 6_500),
        (15, "Décaissement", "Services", "Services externes (maintenance, IT)", 9_000),
        (17, "Encaissement", "Ventes", "Ventes comptoir — semaine 3", 68_000),
        (20, "Décaissement", "Impôts et taxes", "TVA et taxes locales", 24_000),
        (22, "Décaissement", "Achats", "Réapprovisionnement dépôt", 83_000),
        (24, "Encaissement", "Ventes", "Ventes comptoir — semaine 4", 68_000),
        (26, "Décaissement", "Transport", "Transport et logistique", 6_500),
        (28, "Décaissement", "Salaires", "Salaires du personnel", 96_000),
    ]

    for offset in range(-3, 1):
        base = finance.add_months(mois_en_cours, offset)
        for jour, tx_type, categorie, description, montant in templates:
            d = _jour(base, jour)
            if d > limite or d < premier_mois:
                continue
            lignes.append(
                {
                    "date": d,
                    "type": tx_type,
                    "category": categorie,
                    "description": description,
                    "amount": montant,
                    "status": "Réalisé",
                    "expected_date": None,
                    "party": "Divers clients" if tx_type == "Encaissement" else "Divers fournisseurs",
                    "reference": f"M{base.month:02d}-{jour:02d}",
                }
            )

    # Operations exceptionnelles du passe (expliquent la baisse de tresorerie)
    ponctuels = [
        (
            today - timedelta(days=72),
            "Décaissement",
            "Achats",
            "Acquisition d'un camion de livraison (investissement)",
            250_000,
            "Concessionnaire Poids Lourds Casa",
            "INV-2026-0042",
        ),
        (
            today - timedelta(days=55),
            "Décaissement",
            "Impôts et taxes",
            "Acompte d'impôt sur les sociétés",
            60_000,
            "Direction Générale des Impôts",
            "IS-ACOMPTE",
        ),
    ]
    for d, tx_type, categorie, description, montant, tiers, reference in ponctuels:
        if premier_mois <= d <= limite:
            lignes.append(
                {
                    "date": d,
                    "type": tx_type,
                    "category": categorie,
                    "description": description,
                    "amount": montant,
                    "status": "Réalisé",
                    "expected_date": None,
                    "party": tiers,
                    "reference": reference,
                }
            )
    return lignes


def _factures_demo(today: date) -> list[dict]:
    annee = today.year
    return [
        # --- Factures clients ---
        {
            "number": f"FA-{annee}-0001",
            "type": "Client",
            "party": "Marrakech Retail SARL",
            "issue_date": today - timedelta(days=38),
            "due_date": today + timedelta(days=8),
            "total": 96_000,
            "notes": "Commande de palettes de boissons",
            "paiements": [(today - timedelta(days=15), 40_000, "Acompte 40 000 MAD")],
        },
        {
            "number": f"FA-{annee}-0002",
            "type": "Client",
            "party": "Casablanca BTP SA",
            "issue_date": today - timedelta(days=45),
            "due_date": today - timedelta(days=10),
            "total": 145_000,
            "notes": "Livraison chantier — impayé à relancer",
            "paiements": [],
        },
        {
            "number": f"FA-{annee}-0003",
            "type": "Client",
            "party": "Agadir Négoce SARL",
            "issue_date": today - timedelta(days=60),
            "due_date": today - timedelta(days=12),
            "total": 62_000,
            "notes": "Facture soldée",
            "paiements": [(today - timedelta(days=14), 62_000, "Règlement intégral")],
        },
        {
            "number": f"FA-{annee}-0004",
            "type": "Client",
            "party": "Fès Commerce SARL",
            "issue_date": today - timedelta(days=20),
            "due_date": today + timedelta(days=24),
            "total": 210_000,
            "notes": "Gros contrat trimestriel",
            "paiements": [],
        },
        {
            "number": f"FA-{annee}-0005",
            "type": "Client",
            "party": "Tanger Import SARL",
            "issue_date": today - timedelta(days=50),
            "due_date": today + timedelta(days=40),
            "total": 54_000,
            "notes": "Paiement partiel reçu",
            "paiements": [(today - timedelta(days=22), 20_000, "Acompte 20 000 MAD")],
        },
        {
            "number": f"FA-{annee}-0006",
            "type": "Client",
            "party": "Rabat Distribution SARL",
            "issue_date": today - timedelta(days=70),
            "due_date": today - timedelta(days=25),
            "total": 88_000,
            "notes": "Facture soldée",
            "paiements": [(today - timedelta(days=30), 88_000, "Règlement intégral")],
        },
        # --- Factures fournisseurs ---
        {
            "number": f"FF-{annee}-0001",
            "type": "Fournisseur",
            "party": "Sonasid Acier",
            "issue_date": today - timedelta(days=20),
            "due_date": today + timedelta(days=6),
            "total": 65_000,
            "notes": "Matières premières",
            "paiements": [],
        },
        {
            "number": f"FF-{annee}-0002",
            "type": "Fournisseur",
            "party": "Lesieur Cristal",
            "issue_date": today - timedelta(days=30),
            "due_date": today + timedelta(days=13),
            "total": 42_000,
            "notes": "Huiles et corps gras",
            "paiements": [(today - timedelta(days=9), 12_000, "Acompte 12 000 MAD")],
        },
        {
            "number": f"FF-{annee}-0003",
            "type": "Fournisseur",
            "party": "Total Maroc",
            "issue_date": today - timedelta(days=25),
            "due_date": today - timedelta(days=2),
            "total": 14_000,
            "notes": "Carburant flotte de camions — échéance dépassée",
            "paiements": [],
        },
        {
            "number": f"FF-{annee}-0004",
            "type": "Fournisseur",
            "party": "Oulmès Boissons",
            "issue_date": today - timedelta(days=15),
            "due_date": today + timedelta(days=20),
            "total": 88_000,
            "notes": "Réassort important",
            "paiements": [],
        },
        {
            "number": f"FF-{annee}-0005",
            "type": "Fournisseur",
            "party": "ElectroPlanet",
            "issue_date": today - timedelta(days=10),
            "due_date": today + timedelta(days=32),
            "total": 23_000,
            "notes": "Matériel informatique",
            "paiements": [(today - timedelta(days=5), 5_000, "Acompte 5 000 MAD")],
        },
        {
            "number": f"FF-{annee}-0006",
            "type": "Fournisseur",
            "party": "Marjane Pro",
            "issue_date": today - timedelta(days=55),
            "due_date": today - timedelta(days=30),
            "total": 90_000,
            "notes": "Facture soldée",
            "paiements": [(today - timedelta(days=33), 90_000, "Règlement intégral")],
        },
    ]


def _transactions_prevues(today: date) -> list[dict]:
    return [
        {
            "date": today - timedelta(days=5),
            "type": "Décaissement",
            "category": "Achats",
            "description": "Solde fournisseur produits alimentaires",
            "amount": 38_000,
            "status": "En retard",
            "expected_date": today - timedelta(days=5),
            "party": "Grossiste Alimentaire Atlas",
            "reference": "CMD-1180",
        },
        {
            "date": today + timedelta(days=4),
            "type": "Décaissement",
            "category": "Loyer",
            "description": "Loyer entrepôt Casablanca",
            "amount": 18_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=4),
            "party": "SCI Anfa Immobilier",
            "reference": "BAIL-2024",
        },
        {
            "date": today + timedelta(days=7),
            "type": "Décaissement",
            "category": "Achats",
            "description": "Commande de réassort (contre remboursement)",
            "amount": 92_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=7),
            "party": "Centrale d'achat Chaouia",
            "reference": "CMD-1201",
        },
        {
            "date": today + timedelta(days=12),
            "type": "Décaissement",
            "category": "Salaires",
            "description": "Salaires et charges du personnel",
            "amount": 96_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=12),
            "party": "Personnel",
            "reference": "PAIE",
        },
        {
            "date": today + timedelta(days=15),
            "type": "Décaissement",
            "category": "Impôts et taxes",
            "description": "TVA à payer et cotisations CNSS",
            "amount": 42_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=15),
            "party": "Direction Générale des Impôts",
            "reference": "TVA-Q",
        },
        {
            "date": today + timedelta(days=18),
            "type": "Décaissement",
            "category": "Achats",
            "description": "Réapprovisionnement dépôt de Casablanca",
            "amount": 55_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=18),
            "party": "Centrale d'achat Chaouia",
            "reference": "CMD-1205",
        },
        {
            "date": today + timedelta(days=26),
            "type": "Décaissement",
            "category": "Transport",
            "description": "Transport routier mois en cours",
            "amount": 7_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=26),
            "party": "TransLogistique Maroc",
            "reference": "TR-88",
        },
        {
            "date": today + timedelta(days=27),
            "type": "Décaissement",
            "category": "Services",
            "description": "Abonnement logiciel de gestion et maintenance",
            "amount": 11_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=27),
            "party": "SaaS Maroc",
            "reference": "AB-SaaS",
        },
        {
            "date": today - timedelta(days=8),
            "type": "Encaissement",
            "category": "Ventes",
            "description": "Règlement client en retard (Souss Agrégats)",
            "amount": 30_000,
            "status": "En retard",
            "expected_date": today - timedelta(days=8),
            "party": "Souss Agrégats",
            "reference": "FAC-0955",
        },
        {
            "date": today + timedelta(days=9),
            "type": "Encaissement",
            "category": "Ventes",
            "description": "Acompte commande Fès Commerce",
            "amount": 65_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=9),
            "party": "Fès Commerce SARL",
            "reference": "AC-441",
        },
        {
            "date": today + timedelta(days=21),
            "type": "Encaissement",
            "category": "Ventes",
            "description": "Encaissement marchés régionaux",
            "amount": 75_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=21),
            "party": "Divers clients",
            "reference": "PREV-21",
        },
        {
            "date": today + timedelta(days=34),
            "type": "Encaissement",
            "category": "Ventes",
            "description": "Encaissement prévisionnel fin de mois",
            "amount": 90_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=34),
            "party": "Divers clients",
            "reference": "PREV-34",
        },
        {
            "date": today + timedelta(days=45),
            "type": "Décaissement",
            "category": "Achats",
            "description": "Commande trimestrielle programme fêtes",
            "amount": 120_000,
            "status": "Prévu",
            "expected_date": today + timedelta(days=45),
            "party": "Centrale d'achat Chaouia",
            "reference": "CMD-1210",
        },
    ]


def load_demo_data(conn, today: Optional[date] = None) -> dict:
    """Charge (ou recharge) le jeu de donnees de demonstration."""
    today = today or date.today()

    db.clear_all_data(conn)
    db.update_settings(
        conn,
        company_name="Atlas Distribution SARL",
        currency="MAD",
        min_cash_threshold=SEUIL_DEMO,
        opening_cash=SOLDE_HISTORIQUE,
        opening_cash_date=today - timedelta(days=120),
        demo_mode=1,
    )

    # 1. Factures (sans paiement initial)
    ids_factures: dict[str, tuple[int, dict]] = {}
    for facture in _factures_demo(today):
        identifiant = db.add_invoice(
            conn,
            {
                "number": facture["number"],
                "type": facture["type"],
                "party": facture["party"],
                "issue_date": facture["issue_date"],
                "due_date": facture["due_date"],
                "total": facture["total"],
                "paid": 0,
                "notes": facture["notes"],
            },
        )
        ids_factures[facture["number"]] = (identifiant, facture)

    # 2. Transactions realisees (historique)
    db.add_transactions_bulk(conn, _historique(today))

    # 3. Paiements de factures (creent les transactions reelles correspondantes)
    paiements_crees = 0
    for numero, (identifiant, facture) in ids_factures.items():
        for date_paiement, montant, note in facture["paiements"]:
            db.record_payment(conn, identifiant, montant, date_paiement, note)
            paiements_crees += 1

    # 4. Transactions prevues et en retard
    db.add_transactions_bulk(conn, _transactions_prevues(today))

    # 5. Calibrage du solde d'ouverture pour viser la tresorerie de demonstration
    transactions = db.list_transactions(conn)
    somme_reelle = sum(
        finance.to_decimal(finance.signed_amount(tx))
        for tx in transactions
        if finance.is_actual(tx)
    )
    solde_ouverture = finance.money(
        finance.to_decimal(TARGET_CASH_TODAY) - somme_reelle
    )
    db.update_settings(conn, opening_cash=solde_ouverture)

    db.refresh_invoice_statuses(conn, today)

    factures = db.list_invoices(conn)
    stats = db.database_stats(conn)
    return {
        "company": "Atlas Distribution SARL",
        "currency": "MAD",
        "opening_cash": solde_ouverture,
        "actual_cash": finance.actual_cash(db.get_settings(conn), transactions),
        "transactions": stats["transactions"],
        "completed_transactions": sum(1 for tx in transactions if finance.is_actual(tx)),
        "planned_transactions": sum(1 for tx in transactions if not finance.is_actual(tx)),
        "invoices": stats["invoices"],
        "client_invoices": sum(1 for f in factures if f["type"] == "Client"),
        "supplier_invoices": sum(1 for f in factures if f["type"] == "Fournisseur"),
        "payments": paiements_crees,
        "receivables": finance.total_receivables(factures),
        "payables": finance.total_payables(factures),
    }
