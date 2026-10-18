"""Assistant financier local (base sur des regles, sans IA externe).

Ce module ne fabrique jamais de montants : tous les chiffres proviennent des
fonctions de `finance.py` appliquees aux donnees reelles de l'application.

L'architecture est prete pour un futur fournisseur d'IA externe : il suffirait
d'implementer une classe exposant `repondre(question, contexte)` et de la
retourner dans `get_provider()`.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Optional

import finance

SUGGESTIONS = [
    "Quelle est ma situation de trésorerie ?",
    "Quelles sont mes factures clients en retard ?",
    "Quels paiements dois-je prévoir cette semaine ?",
    "Quel est mon flux net ce mois-ci ?",
    "Quel est mon risque de manque de liquidités ?",
    "Que se passe-t-il si un client paie avec 15 jours de retard ?",
    "Que se passe-t-il si mes dépenses augmentent de 10 % ?",
]


def _sans_accent(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _contient(texte: str, *mots: str) -> bool:
    return any(mot in texte for mot in mots)


def _montant_signe(valeur: float, devise: str = "MAD") -> str:
    return finance.money_str(valeur, devise)


class AssistantLocal:
    """Moteur de reponses a base de regles (deterministe, hors ligne)."""

    nom = "Assistant local CashFlow AI (moteur de règles, sans IA externe)"

    def repondre(self, question: str, contexte: dict) -> dict:
        return repondre(question, contexte)


def get_provider() -> AssistantLocal:
    """Retourne le fournisseur de reponses actif (local par defaut)."""
    return AssistantLocal()


# ---------------------------------------------------------------------------
# Reponses
# ---------------------------------------------------------------------------
def _kpi_contexte(contexte: dict) -> dict:
    settings = contexte["settings"]
    transactions = contexte["transactions"]
    factures = contexte["invoices"]
    today = contexte.get("today") or date.today()
    horizon = contexte.get("horizon_days", 30)
    delai = contexte.get("collection_delay", finance.DEFAULT_COLLECTION_DELAY)
    prevision = finance.build_forecast(
        settings, transactions, factures, today, horizon, delai
    )
    return {
        "settings": settings,
        "transactions": transactions,
        "invoices": factures,
        "today": today,
        "devise": settings.get("currency") or "MAD",
        "tresorerie": finance.actual_cash(settings, transactions),
        "prevision": prevision,
        "kpi": finance.forecast_kpis(prevision),
        "creances": finance.total_receivables(factures),
        "dettes": finance.total_payables(factures),
    }


def _reponse_situation(ctx: dict) -> dict:
    devise = ctx["devise"]
    seuil = ctx["settings"].get("min_cash_threshold") or 0
    mois_debut, mois_fin = finance.month_bounds(ctx["today"])
    totaux = finance.cash_totals(ctx["transactions"], mois_debut, mois_fin)
    kpi = ctx["kpi"]
    ecart = ctx["tresorerie"] - seuil
    texte = (
        f"**Trésorerie réelle au {finance.format_date_fr(ctx['today'])} : "
        f"{finance.money_str(ctx['tresorerie'], devise)}**\n\n"
        f"- Seuil de sécurité défini : {finance.money_str(seuil, devise)} "
        f"({'marge de ' + finance.money_str(ecart, devise) if ecart >= 0 else 'déficit de ' + finance.money_str(-ecart, devise)})\n"
        f"- Créances clients à encaisser : {finance.money_str(ctx['creances'], devise)}\n"
        f"- Dettes fournisseurs à payer : {finance.money_str(ctx['dettes'], devise)}\n"
        f"- Flux net réalisé depuis le 1er du mois : {finance.money_str(totaux['net'], devise)} "
        f"(entrées {finance.money_str(totaux['inflows'], devise)} / "
        f"sorties {finance.money_str(totaux['outflows'], devise)})\n"
        f"- Trésorerie projetée à {kpi['horizon_days']} jours : "
        f"{finance.money_str(kpi['final_cash'], devise)} "
        f"(minimum {finance.money_str(kpi['min_cash'], devise)} le "
        f"{finance.format_date_fr(kpi['min_cash_date'])})"
    )
    if kpi["first_negative_date"]:
        texte += (
            f"\n- **Point de vigilance** : la trésorerie projetée devient négative le "
            f"{finance.format_date_fr(kpi['first_negative_date'])}."
        )
    return {
        "titre": "Situation de trésorerie",
        "reponse": texte,
        "donnees": [
            ("Trésorerie réelle", finance.money_str(ctx["tresorerie"], devise)),
            ("Seuil de sécurité", finance.money_str(seuil, devise)),
            ("Encaissements du mois", finance.money_str(totaux["inflows"], devise)),
            ("Décaissements du mois", finance.money_str(totaux["outflows"], devise)),
            ("Flux net du mois", finance.money_str(totaux["net"], devise)),
            ("Créances clients", finance.money_str(ctx["creances"], devise)),
            ("Dettes fournisseurs", finance.money_str(ctx["dettes"], devise)),
            ("Trésorerie projetée", finance.money_str(kpi["final_cash"], devise)),
        ],
        "periode": f"Analyse au {finance.format_date_fr(ctx['today'])} "
        f"(prévision {kpi['horizon_days']} jours)",
        "source": "finance.actual_cash / finance.cash_totals / finance.build_forecast",
    }


def _reponse_retards(ctx: dict) -> dict:
    devise = ctx["devise"]
    today = ctx["today"]
    retards = finance.overdue_invoices(ctx["invoices"], today, inv_type="Client")
    if not retards:
        return {
            "titre": "Factures clients en retard",
            "reponse": "Aucune facture client n'est en retard d'échéance dans la base actuelle.",
            "donnees": [("Factures clients en retard", "0")],
            "periode": f"Au {finance.format_date_fr(today)}",
            "source": "finance.overdue_invoices",
        }
    total = sum(finance.to_decimal(f["remaining"]) for f in retards)
    lignes = [
        f"| {f['number']} | {f['party']} | {finance.format_date_fr(f['due_date'])} | "
        f"{finance.money_str(f['remaining'], devise)} | {finance.overdue_days(f, today)} j |"
        for f in retards
    ]
    tableau = (
        "| Facture | Client | Échéance | Restant dû | Retard |\n"
        "|---|---|---|---|---|\n" + "\n".join(lignes)
    )
    texte = (
        f"**{len(retards)} facture(s) client en retard pour un total de "
        f"{finance.money_str(total, devise)}.**\n\n{tableau}\n\n"
        f"Rappel : ces montants sont comptés dans les prévisions avec un délai estimé "
        f"de recouvrement de {ctx['prevision']['collection_delay']} jours, "
        f"mais ils ne sont **pas** dans la trésorerie réelle."
    )
    return {
        "titre": "Factures clients en retard",
        "reponse": texte,
        "donnees": [
            ("Nombre de factures en retard", str(len(retards))),
            ("Montant total en retard", finance.money_str(total, devise)),
        ],
        "periode": f"Au {finance.format_date_fr(today)}",
        "source": "finance.overdue_invoices + finance.invoice_remaining",
    }


def _reponse_paiements_semaine(ctx: dict) -> dict:
    devise = ctx["devise"]
    today = ctx["today"]
    factures = finance.upcoming_payables(ctx["invoices"], today, days=7)
    prevues = [
        tx
        for tx in ctx["transactions"]
        if not finance.is_actual(tx)
        and tx.get("type") == "Décaissement"
        and finance.effective_date(tx) is not None
        and finance.effective_date(tx) <= today + timedelta(days=7)
    ]
    total_factures = sum(finance.to_decimal(f["remaining"]) for f in factures)
    total_prevues = sum(finance.to_decimal(tx["amount"]) for tx in prevues)
    total = finance.money(to_decimal_sum(total_factures, total_prevues))

    lignes = []
    for f in factures:
        lignes.append(
            f"- Facture {f['number']} — {f['party']} : "
            f"{finance.money_str(f['remaining'], devise)} le "
            f"{finance.format_date_fr(f['due_date'])}"
        )
    for tx in sorted(prevues, key=lambda t: finance.effective_date(t)):
        lignes.append(
            f"- Décaissement prévu — {tx.get('description') or tx.get('category')} : "
            f"{finance.money_str(tx['amount'], devise)} le "
            f"{finance.format_date_fr(finance.effective_date(tx))}"
        )
    detail = "\n".join(lignes) if lignes else "Aucun décaissement identifié."
    texte = (
        f"**Sorties de trésorerie à prévoir dans les 7 jours : "
        f"{finance.money_str(total, devise)}**\n\n{detail}\n\n"
        f"Trésorerie réelle disponible : {finance.money_str(ctx['tresorerie'], devise)}."
    )
    return {
        "titre": "Paiements à prévoir cette semaine",
        "reponse": texte,
        "donnees": [
            ("Fournisseurs à payer (factures)", finance.money_str(total_factures, devise)),
            ("Décaissements prévus (saisis)", finance.money_str(total_prevues, devise)),
            ("Total à prévoir", finance.money_str(total, devise)),
            ("Trésorerie disponible", finance.money_str(ctx["tresorerie"], devise)),
        ],
        "periode": f"Du {finance.format_date_fr(today)} au "
        f"{finance.format_date_fr(today + timedelta(days=7))}",
        "source": "finance.upcoming_payables + transactions prévues",
    }


def to_decimal_sum(a, b):
    return finance.to_decimal(a) + finance.to_decimal(b)


def _reponse_flux_mois(ctx: dict) -> dict:
    devise = ctx["devise"]
    debut, fin = finance.month_bounds(ctx["today"])
    totaux = finance.cash_totals(ctx["transactions"], debut, fin)
    categories = finance.balances_by_category(ctx["transactions"], debut, fin)
    lignes = [
        f"- {c['category']} : entrées {finance.money_str(c['inflows'], devise)} / "
        f"sorties {finance.money_str(c['outflows'], devise)} / net "
        f"{finance.money_str(c['net'], devise)}"
        for c in categories[:6]
    ]
    tendance = "positif" if totaux["net"] >= 0 else "négatif"
    texte = (
        f"**Flux net réalisé en {finance.month_label_fr(ctx['today'])} : "
        f"{finance.money_str(totaux['net'], devise)} ({tendance}).**\n\n"
        f"- Encaissements réalisés : {finance.money_str(totaux['inflows'], devise)}\n"
        f"- Décaissements réalisés : {finance.money_str(totaux['outflows'], devise)}\n\n"
        f"Principales catégories :\n" + ("\n".join(lignes) if lignes else "- Aucun mouvement ce mois.")
    )
    return {
        "titre": "Flux net du mois",
        "reponse": texte,
        "donnees": [
            ("Période", f"{finance.format_date_fr(debut)} → {finance.format_date_fr(fin)}"),
            ("Encaissements", finance.money_str(totaux["inflows"], devise)),
            ("Décaissements", finance.money_str(totaux["outflows"], devise)),
            ("Flux net", finance.money_str(totaux["net"], devise)),
        ],
        "periode": f"{finance.format_date_fr(debut)} → {finance.format_date_fr(fin)}",
        "source": "finance.cash_totals / finance.balances_by_category",
    }


def _reponse_risque(ctx: dict) -> dict:
    devise = ctx["devise"]
    kpi = ctx["kpi"]
    risque = finance.liquidity_risk_score(
        ctx["settings"], ctx["transactions"], ctx["invoices"], ctx["prevision"]
    )
    seuil = finance.to_decimal(ctx["settings"].get("min_cash_threshold") or 0)
    elements = [
        f"- Score de risque de liquidité : **{risque['score']}/100** ({risque['label']})",
        f"- Trésorerie réelle : {finance.money_str(ctx['tresorerie'], devise)}",
        f"- Minimum projeté sur {kpi['horizon_days']} jours : "
        f"{finance.money_str(kpi['min_cash'], devise)} le "
        f"{finance.format_date_fr(kpi['min_cash_date'])}",
        f"- Jours sous le seuil de {finance.money_str(seuil, devise)} : "
        f"{kpi['days_below_threshold']}",
    ]
    if kpi["first_negative_date"]:
        elements.append(
            f"- Première date de trésorerie négative : "
            f"**{finance.format_date_fr(kpi['first_negative_date'])}**"
        )
    retards = finance.overdue_invoices(ctx["invoices"], ctx["today"], inv_type="Client")
    if retards:
        total = sum(finance.to_decimal(f["remaining"]) for f in retards)
        elements.append(
            f"- {len(retards)} facture(s) client en retard pour "
            f"{finance.money_str(total, devise)} (recouvrement à relancer)"
        )
    texte = (
        "**Évaluation du risque de manque de liquidités**\n\n" + "\n".join(elements) + "\n\n"
        "Méthode : comparaison du minimum projeté avec le seuil de sécurité, "
        "détection d'une trésorerie négative, nombre de jours sous le seuil et "
        "retards de recouvrement. Les montants futurs restent des estimations."
    )
    return {
        "titre": "Risque de liquidité",
        "reponse": texte,
        "donnees": [
            ("Score de risque", f"{risque['score']}/100"),
            ("Niveau", risque["label"]),
            ("Minimum projeté", finance.money_str(kpi["min_cash"], devise)),
            ("Jours sous le seuil", str(kpi["days_below_threshold"])),
        ],
        "periode": f"Prévision {kpi['horizon_days']} jours à partir du "
        f"{finance.format_date_fr(ctx['today'])}",
        "source": "finance.liquidity_risk_score / finance.build_forecast",
    }


def _reponse_scenario_retard(ctx: dict, jours: int) -> dict:
    devise = ctx["devise"]
    today = ctx["today"]
    horizon = ctx["kpi"]["horizon_days"]
    base = ctx["prevision"]
    entrees = [it for it in base["items"] if it["direction"] == "in"]
    if not entrees:
        return {
            "titre": "Simulation : retard de paiement client",
            "reponse": "Aucun encaissement attendu dans l'horizon de prévision : "
            "je ne peux pas simuler de retard.",
            "donnees": [],
            "periode": f"Aujourd'hui : {finance.format_date_fr(today)}",
            "source": "finance.delay_item",
        }
    cible = max(entrees, key=lambda it: it["amount"])
    nouvelles_tx, nouvelles_factures = finance.delay_item(
        ctx["transactions"], ctx["invoices"], cible, jours
    )
    scenario = finance.build_forecast(
        ctx["settings"], nouvelles_tx, nouvelles_factures, today, horizon,
        base["collection_delay"],
    )
    comparaison = finance.compare_forecasts(base, scenario)
    texte = (
        f"**Simulation (hypothèse) : « {cible['label']} » ({cible['party']}) "
        f"payé {jours} jours plus tard.**\n\n"
        f"- Montant concerné : {finance.money_str(cible['amount'], devise)}, "
        f"attendu le {finance.format_date_fr(cible['date'])}\n"
        f"- Trésorerie finale (référence) : "
        f"{finance.money_str(comparaison['base']['final_cash'], devise)}\n"
        f"- Trésorerie finale (scénario) : "
        f"{finance.money_str(comparaison['scenario']['final_cash'], devise)}\n"
        f"- Écart : **{finance.money_str(comparaison['final_delta'], devise)}**\n"
        f"- Minimum projeté : {finance.money_str(comparaison['base']['min_cash'], devise)} → "
        f"{finance.money_str(comparaison['scenario']['min_cash'], devise)}\n"
    )
    if comparaison["scenario_first_negative_date"]:
        texte += (
            f"- Trésorerie négative à partir du "
            f"**{finance.format_date_fr(comparaison['scenario_first_negative_date'])}** "
            f"(référence : "
            f"{finance.format_date_fr(comparaison['base_first_negative_date']) if comparaison['base_first_negative_date'] else 'jamais'})\n"
        )
    texte += (
        f"\nRésultat hypothétique : aucune donnée réelle n'a été modifiée. "
        f"Le paiement est simplement décalé de {jours} jours dans le calcul."
    )
    return {
        "titre": "Simulation : retard de paiement client",
        "reponse": texte,
        "donnees": [
            ("Écart de trésorerie finale", finance.money_str(comparaison["final_delta"], devise)),
            ("Minimum scénario", finance.money_str(comparaison["scenario"]["min_cash"], devise)),
            ("Jours sous le seuil (scénario)",
             str(comparaison["scenario"]["days_below_threshold"])),
        ],
        "periode": f"Horizon {horizon} jours à partir du {finance.format_date_fr(today)}",
        "source": "finance.delay_item + finance.compare_forecasts (hypothèse, aucune écriture)",
    }


def _reponse_scenario_depenses(ctx: dict, pourcentage: float) -> dict:
    devise = ctx["devise"]
    today = ctx["today"]
    horizon = ctx["kpi"]["horizon_days"]
    base = ctx["prevision"]
    nouvelles_tx = finance.scale_planned_expenses(ctx["transactions"], pourcentage)
    scenario = finance.build_forecast(
        ctx["settings"], nouvelles_tx, ctx["invoices"], today, horizon,
        base["collection_delay"],
    )
    comparaison = finance.compare_forecasts(base, scenario)
    texte = (
        f"**Simulation (hypothèse) : augmentation de {pourcentage:.0f} % des "
        f"décaissements prévus.**\n\n"
        f"- Décaissements prévus (référence) : "
        f"{finance.money_str(comparaison['base']['total_outflows'], devise)}\n"
        f"- Décaissements prévus (scénario) : "
        f"{finance.money_str(comparaison['scenario']['total_outflows'], devise)}\n"
        f"- Trésorerie finale : {finance.money_str(comparaison['base']['final_cash'], devise)} → "
        f"{finance.money_str(comparaison['scenario']['final_cash'], devise)} "
        f"({finance.money_str(comparaison['final_delta'], devise)})\n"
        f"- Minimum projeté : {finance.money_str(comparaison['base']['min_cash'], devise)} → "
        f"{finance.money_str(comparaison['scenario']['min_cash'], devise)}\n"
        f"- Jours sous le seuil : {comparaison['base']['days_below_threshold']} → "
        f"{comparaison['scenario']['days_below_threshold']}\n\n"
        "Résultat hypothétique : seules des copies ont été recalculées, "
        "les données enregistrées restent inchangées."
    )
    return {
        "titre": "Simulation : hausse des dépenses",
        "reponse": texte,
        "donnees": [
            ("Hausse appliquée", f"{pourcentage:.0f} %"),
            ("Écart de trésorerie finale", finance.money_str(comparaison["final_delta"], devise)),
            ("Minimum scénario", finance.money_str(comparaison["scenario"]["min_cash"], devise)),
        ],
        "periode": f"Horizon {horizon} jours à partir du {finance.format_date_fr(today)}",
        "source": "finance.scale_planned_expenses (hypothèse, aucune écriture)",
    }


def _reponse_creances(ctx: dict) -> dict:
    devise = ctx["devise"]
    today = ctx["today"]
    factures = [
        f
        for f in ctx["invoices"]
        if f["type"] == "Client" and finance.to_decimal(f["remaining"]) > 0
    ]
    factures.sort(key=lambda f: f["due_date"] or today)
    lignes = [
        f"- {f['number']} — {f['party']} : {finance.money_str(f['remaining'], devise)} "
        f"(échéance {finance.format_date_fr(f['due_date'])}, statut "
        f"{finance.compute_invoice_status(f, today)})"
        for f in factures[:10]
    ]
    texte = (
        f"**Créances clients restantes : {finance.money_str(ctx['creances'], devise)} "
        f"sur {len(factures)} facture(s) non soldée(s).**\n\n"
        + ("\n".join(lignes) if lignes else "- Aucune facture client non soldée.")
    )
    return {
        "titre": "Créances clients",
        "reponse": texte,
        "donnees": [("Total à encaisser", finance.money_str(ctx["creances"], devise))],
        "periode": f"Au {finance.format_date_fr(today)}",
        "source": "finance.total_receivables",
    }


def _reponse_capacites(ctx: dict) -> dict:
    liste = "\n".join(f"- {q}" for q in SUGGESTIONS)
    return {
        "titre": "Ce que je peux répondre",
        "reponse": (
            "Je suis un assistant **local et déterministe** (moteur de règles, sans IA "
            "externe). Je réponds à partir des données réelles de votre base :\n\n"
            f"{liste}\n\n"
            "Si votre question ne correspond à aucun de ces cas, je préfère vous le dire "
            "plutôt que d'inventer un chiffre."
        ),
        "donnees": [],
        "periode": f"Au {finance.format_date_fr(ctx['today'])}",
        "source": "assistant local (règles)",
    }


def repondre(question: str, contexte: dict) -> dict:
    """Retourne une reponse structuree a une question en francais."""
    texte = _sans_accent(question or "").strip()
    ctx = _kpi_contexte(contexte)
    if not texte:
        return _reponse_capacites(ctx)

    jours = 15
    correspondance = re.search(r"(\d{1,3})\s*(jours|jour|j)\b", texte)
    if correspondance:
        jours = max(1, min(120, int(correspondance.group(1))))

    pourcentage = 10.0
    correspondance_pct = re.search(r"(\d{1,3})\s*(%|pour\s?cent)", texte)
    if correspondance_pct:
        pourcentage = max(1.0, min(200.0, float(correspondance_pct.group(1))))

    scenario = _contient(texte, "si ", "que se passe", "et si", "simul")

    if _contient(texte, "bonjour", "salut", "salam", "bonsoir", "aide", "help",
                 "que peux tu", "que sais tu", "capacite"):
        return _reponse_capacites(ctx)

    if _contient(texte, "retard") and (scenario or _contient(texte, "paie", "paiement", "client")):
        if scenario:
            return _reponse_scenario_retard(ctx, jours)

    if _contient(texte, "facture") and _contient(texte, "retard", "impaye", "recouvr", "relanc"):
        return _reponse_retards(ctx)

    if _contient(texte, "depense", "charge", "cout") and scenario:
        return _reponse_scenario_depenses(ctx, pourcentage)

    if _contient(texte, "risque", "liquidite", "manque", "tension", "danger", "seuil"):
        return _reponse_risque(ctx)

    if _contient(texte, "cette semaine", "7 jours", "sept jours", "a prevoir", "a payer",
                 "paiement") and _contient(texte, "prevoir", "semaine", "payer", "paiement", "fournisseur"):
        return _reponse_paiements_semaine(ctx)

    if _contient(texte, "flux net", "resultat", "net ce mois", "benefice"):
        return _reponse_flux_mois(ctx)

    if _contient(texte, "creance", "encaisser", "doit me payer", "recouvrer") and not _contient(texte, "retard"):
        return _reponse_creances(ctx)

    if _contient(texte, "dette", "fournisseur"):
        return _reponse_paiements_semaine(ctx)

    if _contient(texte, "tresorerie", "situation", "solde", "combien", "cash"):
        return _reponse_situation(ctx)

    return {
        "titre": "Question non prise en charge",
        "reponse": (
            "Je n'ai pas de règle qui corresponde à cette question, et je préfère vous le "
            "dire clairement plutôt que d'inventer un chiffre.\n\n"
            "Essayez une de ces questions :\n\n"
            + "\n".join(f"- {q}" for q in SUGGESTIONS)
            + "\n\n*Assistant local à base de règles : il ne comprend pas le langage "
            "naturel libre, seulement les intentions prévues.*"
        ),
        "donnees": [],
        "periode": f"Au {finance.format_date_fr(ctx['today'])}",
        "source": "assistant local (règles)",
    }
