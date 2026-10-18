"""Moteur de calcul financier de CashFlow AI.

Toutes les fonctions de ce module sont *pures* : elles ne touchent jamais la
base de donnees. Elles recoivent des listes de dictionnaires (transactions,
factures) et renvoient des chiffres. Cela permet de tester la logique
financiere de facon deterministe (voir tests/test_finance.py).

Conventions
-----------
* Une transaction realisee (statut "Réalisé") impacte la tresorerie reelle.
* Une transaction prevue ("Prévu") ou en retard ("En retard") n'impacte
  jamais la tresorerie reelle : elle n'alimente que les previsions.
* Les montants sont calcules en Decimal puis arrondis au centime.
* Une facture n'est jamais un mouvement de tresorerie : seul son reglement
  (transaction liee via invoice_id) l'est.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Optional, Sequence

CENT = Decimal("0.01")
TOLERANCE = Decimal("0.005")
DEFAULT_COLLECTION_DELAY = 7  # delai estime de recouvrement des impayes clients

MONTHS_FR = [
    "janv.", "fevr.", "mars", "avr.", "mai", "juin",
    "juil.", "aout", "sept.", "oct.", "nov.", "dec.",
]

TRANSACTION_TYPES = ("Encaissement", "Décaissement")
TRANSACTION_STATUSES = ("Réalisé", "Prévu", "En retard")
INVOICE_TYPES = ("Client", "Fournisseur")
CATEGORIES_DEFAUT = [
    "Ventes",
    "Achats",
    "Salaires",
    "Loyer",
    "Impôts et taxes",
    "Transport",
    "Services",
    "Autres",
]


# ---------------------------------------------------------------------------
# Utilitaires (montants, dates)
# ---------------------------------------------------------------------------
def to_decimal(value: Any) -> Decimal:
    """Convertit une valeur quelconque en Decimal (accepte '1 500,50')."""
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError(f"Montant invalide : {value!r}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    texte = str(value).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(texte)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Montant invalide : {value!r}") from exc


def money(value: Any) -> float:
    """Arrondit un montant au centime (float) pour l'affichage / le stockage."""
    return float(to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP))


def money_str(value: Any, currency: str = "MAD", decimals: int = 2) -> str:
    """Formate un montant a la francaise : '1 250,00 MAD'."""
    quant = Decimal("0.01") if decimals == 2 else Decimal(1).scaleb(-decimals)
    q = to_decimal(value).quantize(quant, rounding=ROUND_HALF_UP)
    texte = f"{q:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return f"{texte} {currency}"


def pct_str(value: Any) -> str:
    q = to_decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{q:+.1f} %".replace(".", ",")


def format_date_fr(value: Optional[date]) -> str:
    if value is None:
        return "-"
    return value.strftime("%d/%m/%Y")


def month_label_fr(value: date) -> str:
    return f"{MONTHS_FR[value.month - 1]} {value.year}"


def month_bounds(value: date) -> tuple[date, date]:
    first = value.replace(day=1)
    if first.month == 12:
        nxt = first.replace(year=first.year + 1, month=1)
    else:
        nxt = first.replace(month=first.month + 1)
    return first, nxt - timedelta(days=1)


def add_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(value.day, 28)
    return date(year, month, day)


# ---------------------------------------------------------------------------
# Transactions : notions de base
# ---------------------------------------------------------------------------
def is_actual(tx: dict) -> bool:
    """Vrai si la transaction est realisee (impacte la tresorerie reelle)."""
    return tx.get("status") == "Réalisé"


def is_planned(tx: dict) -> bool:
    return not is_actual(tx)


def signed_amount(tx: dict, actual_only: bool = True) -> Decimal:
    """Montant signe : positif pour un encaissement, negatif pour un decaissement."""
    if actual_only and not is_actual(tx):
        return Decimal("0")
    montant = to_decimal(tx.get("amount"))
    return montant if tx.get("type") == "Encaissement" else -montant


def effective_date(tx: dict) -> Optional[date]:
    """Date qui compte dans les previsions.

    * Réalisé  -> date de l'operation.
    * Prévu / En retard -> date prevue de reglement (sinon date d'operation).
    """
    if is_actual(tx):
        return tx.get("date")
    return tx.get("expected_date") or tx.get("date")


# ---------------------------------------------------------------------------
# Tresorerie reelle
# ---------------------------------------------------------------------------
def actual_cash(settings: dict, transactions: Iterable[dict]) -> float:
    """Tresorerie actuelle = solde d'ouverture + mouvements realises.

    Les transactions prevues ou en retard sont volontairement ignorees.
    """
    solde = to_decimal(settings.get("opening_cash") or 0)
    for tx in transactions:
        solde += signed_amount(tx, actual_only=True)
    return money(solde)


def cash_totals(
    transactions: Iterable[dict],
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    """Totaux des mouvements realises sur une periode (bornes incluses)."""
    entrees = Decimal("0")
    sorties = Decimal("0")
    for tx in transactions:
        if not is_actual(tx):
            continue
        d = tx.get("date")
        if d is None:
            continue
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            continue
        montant = to_decimal(tx.get("amount"))
        if tx.get("type") == "Encaissement":
            entrees += montant
        else:
            sorties += montant
    return {
        "inflows": money(entrees),
        "outflows": money(sorties),
        "net": money(entrees - sorties),
    }


def net_cash_flow(
    transactions: Iterable[dict],
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> float:
    """Flux net de tresorerie realise sur la periode."""
    return cash_totals(transactions, start, end)["net"]


def balances_by_category(
    transactions: Iterable[dict], start: Optional[date] = None, end: Optional[date] = None
) -> list[dict]:
    """Repartition des mouvements realises par categorie."""
    agg: dict[str, dict[str, Decimal]] = {}
    for tx in transactions:
        if not is_actual(tx):
            continue
        d = tx.get("date")
        if d is None:
            continue
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            continue
        cat = tx.get("category") or "Autres"
        item = agg.setdefault(cat, {"in": Decimal("0"), "out": Decimal("0")})
        montant = to_decimal(tx.get("amount"))
        if tx.get("type") == "Encaissement":
            item["in"] += montant
        else:
            item["out"] += montant
    lignes = [
        {
            "category": cat,
            "inflows": money(v["in"]),
            "outflows": money(v["out"]),
            "net": money(v["in"] - v["out"]),
        }
        for cat, v in agg.items()
    ]
    lignes.sort(key=lambda x: abs(x["net"]), reverse=True)
    return lignes


def cash_balance_series(
    settings: dict,
    transactions: Iterable[dict],
    start: date,
    end: date,
) -> list[dict]:
    """Serie journaliere de tresorerie reelle entre deux dates (incluses)."""
    solde = to_decimal(settings.get("opening_cash") or 0)
    mouvements: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    for tx in transactions:
        if not is_actual(tx):
            continue
        d = tx.get("date")
        if d is None:
            continue
        if d < start:
            solde += signed_amount(tx)
        elif d <= end:
            mouvements[d] += signed_amount(tx)

    serie = []
    jour = start
    while jour <= end:
        solde += mouvements.get(jour, Decimal("0"))
        serie.append({"date": jour, "balance": money(solde)})
        jour += timedelta(days=1)
    return serie


def monthly_cash_series(
    transactions: Iterable[dict], today: Optional[date] = None, months: int = 6
) -> list[dict]:
    """Serie mensuelle encaissements / decaissements realises."""
    today = today or date.today()
    cles: list[tuple[int, int]] = []
    for i in range(months - 1, -1, -1):
        d = add_months(today.replace(day=1), -i)
        cles.append((d.year, d.month))

    agg = {c: {"in": Decimal("0"), "out": Decimal("0")} for c in cles}
    for tx in transactions:
        if not is_actual(tx):
            continue
        d = tx.get("date")
        if d is None:
            continue
        cle = (d.year, d.month)
        if cle not in agg:
            continue
        montant = to_decimal(tx.get("amount"))
        agg[cle]["in" if tx.get("type") == "Encaissement" else "out"] += montant

    resultat = []
    for annee, mois in cles:
        entrees = money(agg[(annee, mois)]["in"])
        sorties = money(agg[(annee, mois)]["out"])
        resultat.append(
            {
                "key": f"{annee}-{mois:02d}",
                "label": f"{MONTHS_FR[mois - 1]} {annee}",
                "inflows": entrees,
                "outflows": sorties,
                "net": money(to_decimal(entrees) - to_decimal(sorties)),
            }
        )
    return resultat


# ---------------------------------------------------------------------------
# Factures
# ---------------------------------------------------------------------------
def invoice_remaining(invoice: dict) -> float:
    """Solde restant du = total - deja paye (jamais negatif)."""
    reste = to_decimal(invoice.get("total")) - to_decimal(invoice.get("paid"))
    return money(max(reste, Decimal("0")))


def compute_invoice_status(invoice: dict, today: Optional[date] = None) -> str:
    """Statut calcule : Payée, En retard, Partiellement payée ou Ouverte."""
    today = today or date.today()
    reste = to_decimal(invoice_remaining(invoice))
    paye = to_decimal(invoice.get("paid"))
    echeance = invoice.get("due_date")
    if reste <= TOLERANCE:
        return "Payée"
    if echeance is not None and echeance < today:
        return "En retard"
    if paye > TOLERANCE:
        return "Partiellement payée"
    return "Ouverte"


def total_receivables(invoices: Iterable[dict]) -> float:
    """Creances clients restantes (factures clients non soldees)."""
    total = Decimal("0")
    for inv in invoices:
        if inv.get("type") == "Client":
            total += to_decimal(invoice_remaining(inv))
    return money(total)


def total_payables(invoices: Iterable[dict]) -> float:
    """Dettes fournisseurs restantes."""
    total = Decimal("0")
    for inv in invoices:
        if inv.get("type") == "Fournisseur":
            total += to_decimal(invoice_remaining(inv))
    return money(total)


def overdue_invoices(
    invoices: Iterable[dict], today: Optional[date] = None, inv_type: Optional[str] = None
) -> list[dict]:
    """Factures non soldees dont l'echeance est depassee."""
    today = today or date.today()
    resultat = []
    for inv in invoices:
        if inv_type and inv.get("type") != inv_type:
            continue
        if to_decimal(invoice_remaining(inv)) <= TOLERANCE:
            continue
        echeance = inv.get("due_date")
        if echeance is not None and echeance < today:
            resultat.append(inv)
    resultat.sort(key=lambda x: x.get("due_date") or today)
    return resultat


def overdue_days(invoice: dict, today: Optional[date] = None) -> int:
    today = today or date.today()
    echeance = invoice.get("due_date")
    if echeance is None or echeance >= today:
        return 0
    return (today - echeance).days


def upcoming_payables(
    invoices: Iterable[dict], today: Optional[date] = None, days: int = 7
) -> list[dict]:
    """Factures fournisseurs a regler dans les prochains jours."""
    today = today or date.today()
    limite = today + timedelta(days=days)
    resultat = []
    for inv in invoices:
        if inv.get("type") != "Fournisseur":
            continue
        if to_decimal(invoice_remaining(inv)) <= TOLERANCE:
            continue
        echeance = inv.get("due_date")
        if echeance is not None and echeance <= limite:
            resultat.append(inv)
    resultat.sort(key=lambda x: x.get("due_date") or today)
    return resultat


def upcoming_receipts(
    invoices: Iterable[dict], today: Optional[date] = None, days: int = 7
) -> list[dict]:
    """Factures clients attendues dans les prochains jours."""
    today = today or date.today()
    limite = today + timedelta(days=days)
    resultat = []
    for inv in invoices:
        if inv.get("type") != "Client":
            continue
        if to_decimal(invoice_remaining(inv)) <= TOLERANCE:
            continue
        echeance = inv.get("due_date")
        if echeance is not None and echeance <= limite:
            resultat.append(inv)
    resultat.sort(key=lambda x: x.get("due_date") or today)
    return resultat


# ---------------------------------------------------------------------------
# Previsions de tresorerie (deterministes)
# ---------------------------------------------------------------------------
def _clamp_date(
    value: Optional[date], direction: str, today: date, collection_delay: int
) -> date:
    """Ramene une echeance passee dans la fenetre de prevision.

    * Entree d'argent en retard : attendue dans `collection_delay` jours.
    * Sortie d'argent en retard : consideree comme due immediatement
      (hypothese prudente pour la tresorerie).
    """
    if value is None:
        return today
    if value >= today:
        return value
    if direction == "in":
        return today + timedelta(days=collection_delay)
    return today


def forecast_items(
    transactions: Iterable[dict],
    invoices: Iterable[dict],
    today: Optional[date] = None,
    collection_delay: int = DEFAULT_COLLECTION_DELAY,
) -> list[dict]:
    """Construit la liste des flux attendus sans double comptage.

    Regle anti-double-comptage : si une facture possede deja une transaction
    prevue liee (invoice_id), c'est la transaction qui est utilisee et la
    facture est ignoree.
    """
    today = today or date.today()
    transactions = list(transactions)
    invoices = list(invoices)

    factures_liees = {
        tx.get("invoice_id")
        for tx in transactions
        if tx.get("invoice_id") and not is_actual(tx)
    }

    items: list[dict] = []
    for tx in transactions:
        if is_actual(tx):
            continue
        brute: Optional[date] = effective_date(tx)
        if brute is None:
            continue
        direction = "in" if tx.get("type") == "Encaissement" else "out"
        items.append(
            {
                "date": _clamp_date(brute, direction, today, collection_delay),
                "raw_date": brute,
                "direction": direction,
                "amount": money(tx.get("amount")),
                "label": tx.get("description") or tx.get("category") or "Transaction prévue",
                "category": tx.get("category") or "Autres",
                "party": tx.get("party") or "",
                "source": "transaction",
                "source_id": tx.get("id"),
                "status": tx.get("status") or "Prévu",
                "overdue": brute < today,
            }
        )

    for inv in invoices:
        reste = invoice_remaining(inv)
        if to_decimal(reste) <= TOLERANCE:
            continue
        if inv.get("id") in factures_liees:
            continue  # deja representee par une transaction prevue
        direction = "in" if inv.get("type") == "Client" else "out"
        echeance = inv.get("due_date")
        items.append(
            {
                "date": _clamp_date(echeance, direction, today, collection_delay),
                "raw_date": echeance,
                "direction": direction,
                "amount": reste,
                "label": f"Facture {inv.get('number') or inv.get('id')}",
                "category": "Factures clients" if direction == "in" else "Factures fournisseurs",
                "party": inv.get("party") or "",
                "source": "invoice",
                "source_id": inv.get("id"),
                "status": compute_invoice_status(inv, today),
                "overdue": echeance is not None and echeance < today,
            }
        )

    items.sort(key=lambda x: (x["date"], x["direction"]))
    return items


def build_forecast(
    settings: dict,
    transactions: Iterable[dict],
    invoices: Iterable[dict],
    today: Optional[date] = None,
    horizon_days: int = 30,
    collection_delay: int = DEFAULT_COLLECTION_DELAY,
) -> dict:
    """Prevision journaliere de tresorerie sur `horizon_days` jours.

    Tresorerie projetee = encaissements reels + encaissements attendus
    - decaissements reels - decaissements attendus.
    """
    today = today or date.today()
    horizon_days = int(horizon_days)
    seuil = money(settings.get("min_cash_threshold") or 0)
    solde_ouverture = to_decimal(actual_cash(settings, transactions))
    fin = today + timedelta(days=horizon_days)

    items = forecast_items(transactions, invoices, today, collection_delay)
    items_retenus = [it for it in items if today <= it["date"] <= fin]
    items_hors_fenetre = [it for it in items if it["date"] > fin]

    mouvements: dict[date, dict[str, Decimal]] = defaultdict(
        lambda: {"in": Decimal("0"), "out": Decimal("0")}
    )
    for it in items_retenus:
        mouvements[it["date"]]["in" if it["direction"] == "in" else "out"] += to_decimal(
            it["amount"]
        )

    jours: list[dict] = []
    solde = solde_ouverture
    minimum = solde_ouverture
    date_minimum = today
    premiere_negative: Optional[date] = None
    jours_sous_seuil = 0
    total_entrees = Decimal("0")
    total_sorties = Decimal("0")

    for offset in range(horizon_days + 1):
        jour = today + timedelta(days=offset)
        entrees = mouvements[jour]["in"]
        sorties = mouvements[jour]["out"]
        total_entrees += entrees
        total_sorties += sorties
        solde += entrees - sorties
        cloture = money(solde)
        if cloture < minimum:
            minimum = cloture
            date_minimum = jour
        if cloture < 0 and premiere_negative is None:
            premiere_negative = jour
        if cloture < seuil:
            jours_sous_seuil += 1
        jours.append(
            {
                "date": jour,
                "inflows": money(entrees),
                "outflows": money(sorties),
                "net": money(entrees - sorties),
                "closing": cloture,
                "below_threshold": cloture < seuil,
            }
        )

    return {
        "today": today,
        "horizon_days": horizon_days,
        "end_date": fin,
        "collection_delay": collection_delay,
        "opening_cash": money(solde_ouverture),
        "threshold": seuil,
        "days": jours,
        "items": items_retenus,
        "items_outside_horizon": items_hors_fenetre,
        "total_inflows": money(total_entrees),
        "total_outflows": money(total_sorties),
        "net_flow": money(total_entrees - total_sorties),
        "final_cash": jours[-1]["closing"] if jours else money(solde_ouverture),
        "min_cash": minimum,
        "min_cash_date": date_minimum,
        "first_negative_date": premiere_negative,
        "days_below_threshold": jours_sous_seuil,
        "is_estimated": True,
    }


def forecast_kpis(forecast: dict) -> dict:
    """Indicateurs de synthese d'une prevision."""
    return {
        "opening_cash": forecast["opening_cash"],
        "final_cash": forecast["final_cash"],
        "net_flow": forecast["net_flow"],
        "total_inflows": forecast["total_inflows"],
        "total_outflows": forecast["total_outflows"],
        "min_cash": forecast["min_cash"],
        "min_cash_date": forecast["min_cash_date"],
        "first_negative_date": forecast["first_negative_date"],
        "days_below_threshold": forecast["days_below_threshold"],
        "threshold": forecast["threshold"],
        "horizon_days": forecast["horizon_days"],
    }


# ---------------------------------------------------------------------------
# Simulateur de scenarios (ne modifie jamais les donnees stockees)
# ---------------------------------------------------------------------------
def delay_item(
    transactions: Sequence[dict],
    invoices: Sequence[dict],
    item: dict,
    days: int,
) -> tuple[list[dict], list[dict]]:
    """Retourne des copies ou l'echeance de `item` est decalee de `days` jours."""
    jours = int(days)
    if jours < 0:
        raise ValueError("Le decalage doit etre positif.")
    nouvelles_tx = [dict(tx) for tx in transactions]
    nouvelles_factures = [dict(inv) for inv in invoices]
    nouvelle_date = item["date"] + timedelta(days=jours)

    if item["source"] == "transaction":
        for tx in nouvelles_tx:
            if tx.get("id") == item["source_id"]:
                tx["status"] = "Prévu"
                base = tx.get("date") or item["date"]
                tx["date"] = base if base <= nouvelle_date else nouvelle_date
                tx["expected_date"] = nouvelle_date
                break
    else:
        for inv in nouvelles_factures:
            if inv.get("id") == item["source_id"]:
                inv["due_date"] = nouvelle_date
                break
    return nouvelles_tx, nouvelles_factures


def scale_planned_expenses(
    transactions: Sequence[dict], increase_pct: float
) -> list[dict]:
    """Copie des transactions ou les sorties prevues augmentent de X %."""
    facteur = Decimal("1") + to_decimal(increase_pct) / Decimal("100")
    if facteur < 0:
        raise ValueError("Le pourcentage doit etre positif ou nul.")
    resultat = []
    for tx in transactions:
        copie = dict(tx)
        if not is_actual(copie) and copie.get("type") == "Décaissement":
            copie["amount"] = money(to_decimal(copie.get("amount")) * facteur)
        resultat.append(copie)
    return resultat


def add_planned_expense(
    transactions: Sequence[dict],
    on_date: date,
    amount: float,
    label: str = "Dépense exceptionnelle (simulation)",
    category: str = "Autres",
) -> list[dict]:
    """Copie des transactions + une sortie prevue supplementaire."""
    resultat = [dict(tx) for tx in transactions]
    resultat.append(
        {
            "id": None,
            "date": on_date,
            "type": "Décaissement",
            "category": category,
            "description": label,
            "amount": money(amount),
            "status": "Prévu",
            "expected_date": on_date,
            "party": "Simulation",
            "reference": "SIMULATION",
            "invoice_id": None,
        }
    )
    return resultat


def compare_forecasts(base: dict, scenario: dict) -> dict:
    """Compare une prevision de reference et une prevision simulee."""
    base_kpi = forecast_kpis(base)
    scen_kpi = forecast_kpis(scenario)
    return {
        "base": base_kpi,
        "scenario": scen_kpi,
        "final_delta": money(to_decimal(scen_kpi["final_cash"]) - to_decimal(base_kpi["final_cash"])),
        "min_delta": money(to_decimal(scen_kpi["min_cash"]) - to_decimal(base_kpi["min_cash"])),
        "min_delta_date": scen_kpi["min_cash_date"],
        "extra_days_below_threshold": scen_kpi["days_below_threshold"]
        - base_kpi["days_below_threshold"],
        "base_first_negative_date": base_kpi["first_negative_date"],
        "scenario_first_negative_date": scen_kpi["first_negative_date"],
        "worst_case_min": min(base_kpi["min_cash"], scen_kpi["min_cash"]),
    }


# ---------------------------------------------------------------------------
# Alertes
# ---------------------------------------------------------------------------
def build_alerts(
    settings: dict,
    transactions: Sequence[dict],
    invoices: Sequence[dict],
    forecast: Optional[dict] = None,
    today: Optional[date] = None,
) -> list[dict]:
    """Alertes concretes basees uniquement sur les donnees de l'application."""
    today = today or date.today()
    devise = settings.get("currency") or "MAD"
    seuil = money(settings.get("min_cash_threshold") or 0)
    alertes: list[dict] = []

    tresorerie = actual_cash(settings, transactions)
    if tresorerie < 0:
        alertes.append(
            {
                "level": "danger",
                "title": "Trésorerie actuelle négative",
                "message": f"Le solde réel est de {money_str(tresorerie, devise)}.",
            }
        )
    elif seuil and tresorerie < seuil:
        alertes.append(
            {
                "level": "warning",
                "title": "Trésorerie sous le seuil de sécurité",
                "message": (
                    f"Solde réel {money_str(tresorerie, devise)} < seuil "
                    f"{money_str(seuil, devise)}."
                ),
            }
        )

    if forecast:
        kpi = forecast_kpis(forecast)
        if kpi["first_negative_date"]:
            alertes.append(
                {
                    "level": "danger",
                    "title": "Trésorerie prévisionnelle négative",
                    "message": (
                        f"Le solde projeté devient négatif le "
                        f"{format_date_fr(kpi['first_negative_date'])} "
                        f"(horizon {kpi['horizon_days']} jours)."
                    ),
                }
            )
        if seuil and kpi["min_cash"] < seuil and kpi["days_below_threshold"] > 0:
            alertes.append(
                {
                    "level": "warning" if kpi["min_cash"] >= 0 else "danger",
                    "title": "Seuil de sécurité franchi en prévision",
                    "message": (
                        f"Minimum projeté {money_str(kpi['min_cash'], devise)} le "
                        f"{format_date_fr(kpi['min_cash_date'])} — "
                        f"{kpi['days_below_threshold']} jour(s) sous le seuil "
                        f"de {money_str(seuil, devise)}."
                    ),
                }
            )

    en_retard = overdue_invoices(invoices, today, inv_type="Client")
    if en_retard:
        total = sum(to_decimal(invoice_remaining(i)) for i in en_retard)
        plus_ancienne = en_retard[0]
        alertes.append(
            {
                "level": "danger",
                "title": f"{len(en_retard)} facture(s) client en retard",
                "message": (
                    f"{money_str(total, devise)} à recouvrer. La plus ancienne : "
                    f"{plus_ancienne.get('number')} ({plus_ancienne.get('party')}), "
                    f"{overdue_days(plus_ancienne, today)} jours de retard."
                ),
            }
        )

    fournisseurs = upcoming_payables(invoices, today, days=7)
    if fournisseurs:
        total = sum(to_decimal(invoice_remaining(i)) for i in fournisseurs)
        deja_echues = [
            i for i in fournisseurs if i.get("due_date") and i["due_date"] < today
        ]
        a_venir = [i for i in fournisseurs if i not in deja_echues]
        prochaine = a_venir[0] if a_venir else None
        precision = (
            f"dont {len(deja_echues)} déjà échue(s). "
            if deja_echues and a_venir
            else ("toutes déjà échues. " if deja_echues else "")
        )
        if prochaine is not None:
            precision += (
                f"Prochaine échéance : {prochaine.get('number')} "
                f"({prochaine.get('party')}) le {format_date_fr(prochaine.get('due_date'))}."
            )
        else:
            precision += (
                f"La plus ancienne : {deja_echues[0].get('number')} "
                f"({deja_echues[0].get('party')}) échue depuis "
                f"{overdue_days(deja_echues[0], today)} jours."
            )
        alertes.append(
            {
                "level": "warning",
                "title": "Paiements fournisseurs à prévoir (7 jours)",
                "message": (
                    f"{len(fournisseurs)} facture(s) pour {money_str(total, devise)} à régler, "
                    f"{precision}"
                ),
            }
        )

    retards_prevus = [
        tx
        for tx in transactions
        if tx.get("status") == "En retard"
    ]
    if retards_prevus:
        total = sum(to_decimal(tx.get("amount")) for tx in retards_prevus)
        alertes.append(
            {
                "level": "warning",
                "title": "Opérations prévues en retard",
                "message": (
                    f"{len(retards_prevus)} opération(s) non soldées pour "
                    f"{money_str(total, devise)} : elles ne sont pas comptées "
                    f"dans la trésorerie réelle."
                ),
            }
        )

    # Informations manquantes
    if not to_decimal(settings.get("opening_cash")):
        alertes.append(
            {
                "level": "info",
                "title": "Solde d'ouverture non renseigné",
                "message": "Renseignez le solde d'ouverture dans Rapports et paramètres.",
            }
        )
    if not transactions:
        alertes.append(
            {
                "level": "info",
                "title": "Aucune transaction enregistrée",
                "message": "Ajoutez des transactions ou chargez les données de démonstration.",
            }
        )
    factures_sans_echeance = [i for i in invoices if not i.get("due_date")]
    if factures_sans_echeance:
        alertes.append(
            {
                "level": "info",
                "title": "Factures sans date d'échéance",
                "message": (
                    f"{len(factures_sans_echeance)} facture(s) n'ont pas d'échéance : "
                    "elles ne peuvent pas être datées dans la prévision."
                ),
            }
        )
    if not invoices:
        alertes.append(
            {
                "level": "info",
                "title": "Aucune facture enregistrée",
                "message": "Les créances et dettes ne peuvent pas être calculées.",
            }
        )

    if not alertes:
        alertes.append(
            {
                "level": "success",
                "title": "Aucune alerte",
                "message": "La situation de trésorerie ne présente pas de risque identifié.",
            }
        )
    return alertes


def liquidity_risk_score(
    settings: dict, transactions: Sequence[dict], invoices: Sequence[dict], forecast: dict
) -> dict:
    """Score de risque de liquidite simple (0 = risque faible, 100 = critique)."""
    kpi = forecast_kpis(forecast)
    seuil = to_decimal(settings.get("min_cash_threshold") or 0)
    solde = to_decimal(kpi["min_cash"])
    score = 0
    if kpi["first_negative_date"]:
        score += 55
    if seuil > 0 and solde < seuil:
        score += 25
    if seuil > 0 and solde < 0:
        score += 15
    retards = overdue_invoices(invoices, date.today(), inv_type="Client")
    if retards:
        score += min(20, len(retards) * 7)
    jours = kpi["days_below_threshold"]
    score += min(15, jours)
    score = max(0, min(100, score))
    if score >= 70:
        niveau, libelle = "danger", "Risque élevé"
    elif score >= 40:
        niveau, libelle = "warning", "Risque modéré"
    else:
        niveau, libelle = "success", "Risque faible"
    return {"score": score, "level": niveau, "label": libelle}
