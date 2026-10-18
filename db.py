"""Couche de persistance SQLite de CashFlow AI.

Toutes les requetes sont parametrees (aucune concatenation de SQL) et les
ecritures groupees (facture + paiement + transaction) sont realisees dans une
seule transaction SQLite.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import finance

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "cashflow_ai.db"

TRANSACTION_TYPES = finance.TRANSACTION_TYPES
TRANSACTION_STATUSES = finance.TRANSACTION_STATUSES
INVOICE_TYPES = finance.INVOICE_TYPES
CATEGORIES_DEFAUT = finance.CATEGORIES_DEFAUT

DEFAULT_SETTINGS = {
    "id": 1,
    "company_name": "Atlas Distribution SARL",
    "currency": "MAD",
    "opening_cash": 0.0,
    "opening_cash_date": date.today(),
    "min_cash_threshold": 0.0,
    "demo_mode": 0,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    company_name       TEXT    NOT NULL DEFAULT 'Atlas Distribution SARL',
    currency           TEXT    NOT NULL DEFAULT 'MAD',
    opening_cash       REAL    NOT NULL DEFAULT 0,
    opening_cash_date  TEXT,
    min_cash_threshold REAL    NOT NULL DEFAULT 0,
    demo_mode          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invoices (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL UNIQUE,
    invoice_type TEXT    NOT NULL CHECK (invoice_type IN ('Client', 'Fournisseur')),
    party        TEXT    NOT NULL,
    issue_date   TEXT    NOT NULL,
    due_date     TEXT,
    total_amount REAL    NOT NULL CHECK (total_amount >= 0),
    amount_paid  REAL    NOT NULL DEFAULT 0 CHECK (amount_paid >= 0),
    status       TEXT    NOT NULL DEFAULT 'Ouverte',
    notes        TEXT,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_date       TEXT    NOT NULL,
    tx_type       TEXT    NOT NULL CHECK (tx_type IN ('Encaissement', 'Décaissement')),
    category      TEXT    NOT NULL DEFAULT 'Autres',
    description   TEXT,
    amount        REAL    NOT NULL CHECK (amount > 0),
    status        TEXT    NOT NULL DEFAULT 'Prévu',
    expected_date TEXT,
    party         TEXT,
    reference     TEXT,
    invoice_id    INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id     INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    payment_date   TEXT    NOT NULL,
    amount         REAL    NOT NULL CHECK (amount > 0),
    transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    note           TEXT,
    created_at     TEXT    NOT NULL,
    UNIQUE (invoice_id, payment_date, amount)
);

CREATE INDEX IF NOT EXISTS idx_tx_date   ON transactions (tx_date);
CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions (status);
CREATE INDEX IF NOT EXISTS idx_inv_type  ON invoices (invoice_type);
CREATE INDEX IF NOT EXISTS idx_inv_due   ON invoices (due_date);
CREATE INDEX IF NOT EXISTS idx_pay_inv   ON payments (invoice_id);
"""

_conn: Optional[sqlite3.Connection] = None
_lock = threading.RLock()


# ---------------------------------------------------------------------------
# Connexion / initialisation
# ---------------------------------------------------------------------------
def connect(db_path: Optional[Any] = None) -> sqlite3.Connection:
    """Ouvre une NOUVELLE connexion (utilise par les tests)."""
    if db_path is None:
        cible = DB_PATH
        cible.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(cible), check_same_thread=False)
    elif str(db_path) == ":memory:":
        conn = sqlite3.connect(":memory:", check_same_thread=False)
    else:
        chemin = Path(db_path)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(chemin), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_connection() -> sqlite3.Connection:
    """Connexion partagee de l'application (fichier data/cashflow_ai.db)."""
    global _conn
    with _lock:
        if _conn is None:
            _conn = connect(DB_PATH)
            init_db(_conn)
        return _conn


def close_connection() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def init_db(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Cree les tables si besoin et garantit la ligne de parametres."""
    conn.executescript(SCHEMA)
    ligne = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
    if ligne is None:
        conn.execute(
            """INSERT INTO settings
               (id, company_name, currency, opening_cash, opening_cash_date,
                min_cash_threshold, demo_mode)
               VALUES (1, ?, ?, ?, ?, ?, 0)""",
            (
                DEFAULT_SETTINGS["company_name"],
                DEFAULT_SETTINGS["currency"],
                DEFAULT_SETTINGS["opening_cash"],
                parse_date(DEFAULT_SETTINGS["opening_cash_date"]).isoformat(),
                DEFAULT_SETTINGS["min_cash_threshold"],
            ),
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
def parse_date(value: Any) -> Optional[date]:
    """Convertit une valeur en date (accepte plusieurs formats)."""
    if value is None or value == "" or value == "None":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    texte = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texte, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"Date invalide : {value!r} (formats acceptes : AAAA-MM-JJ ou JJ/MM/AAAA)"
    )


def fmt_date(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Parametres
# ---------------------------------------------------------------------------
def get_settings(conn: sqlite3.Connection) -> dict:
    ligne = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if ligne is None:
        init_db(conn)
        ligne = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return {
        "id": 1,
        "company_name": ligne["company_name"],
        "currency": ligne["currency"],
        "opening_cash": float(ligne["opening_cash"]),
        "opening_cash_date": parse_date(ligne["opening_cash_date"]) or date.today(),
        "min_cash_threshold": float(ligne["min_cash_threshold"]),
        "demo_mode": int(ligne["demo_mode"]),
    }


def update_settings(conn: sqlite3.Connection, **champs: Any) -> dict:
    autorises = {
        "company_name",
        "currency",
        "opening_cash",
        "opening_cash_date",
        "min_cash_threshold",
        "demo_mode",
    }
    inconnus = set(champs) - autorises
    if inconnus:
        raise ValueError(f"Paramètre(s) inconnu(s) : {', '.join(sorted(inconnus))}")

    valeurs: dict[str, Any] = {}
    for cle, valeur in champs.items():
        if cle == "company_name":
            nom = str(valeur or "").strip()
            if not nom:
                raise ValueError("Le nom de l'entreprise ne peut pas être vide.")
            if len(nom) > 120:
                raise ValueError("Le nom de l'entreprise est trop long (120 caractères max).")
            valeurs[cle] = nom
        elif cle == "currency":
            devise = str(valeur or "MAD").strip().upper()[:8]
            valeurs[cle] = devise or "MAD"
        elif cle == "opening_cash":
            montant = finance.to_decimal(valeur)
            if abs(montant) > finance.to_decimal("1000000000000"):
                raise ValueError("Solde d'ouverture hors limites.")
            valeurs[cle] = finance.money(montant)
        elif cle == "min_cash_threshold":
            montant = finance.to_decimal(valeur)
            if montant < 0:
                raise ValueError("Le seuil de sécurité doit être positif.")
            valeurs[cle] = finance.money(montant)
        elif cle == "opening_cash_date":
            valeurs[cle] = fmt_date(parse_date(valeur) or date.today())
        elif cle == "demo_mode":
            valeurs[cle] = 1 if valeur else 0

    if not valeurs:
        return get_settings(conn)

    colonnes = ", ".join(f"{c} = ?" for c in valeurs)
    conn.execute(
        f"UPDATE settings SET {colonnes} WHERE id = 1",  # noqa: S608 - colonnes filtrees
        tuple(valeurs.values()),
    )
    conn.commit()
    return get_settings(conn)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _texte(value: Any, maxi: int, defaut: str = "") -> str:
    if value is None:
        return defaut
    texte = str(value).strip()
    if len(texte) > maxi:
        texte = texte[:maxi]
    return texte


def validate_transaction(data: dict) -> dict:
    """Valide et normalise une transaction. Leve ValueError si invalide."""
    tx_type = _texte(data.get("type"), 20)
    if tx_type not in TRANSACTION_TYPES:
        raise ValueError(
            "Type invalide : utilisez 'Encaissement' ou 'Décaissement'."
        )
    tx_date = parse_date(data.get("date"))
    if tx_date is None:
        raise ValueError("La date de la transaction est obligatoire.")
    statut = _texte(data.get("status"), 20) or "Prévu"
    if statut not in TRANSACTION_STATUSES:
        raise ValueError(
            "Statut invalide : utilisez 'Réalisé', 'Prévu' ou 'En retard'."
        )
    montant = finance.to_decimal(data.get("amount"))
    if montant <= 0:
        raise ValueError("Le montant doit être strictement supérieur à 0.")
    if montant > finance.to_decimal("1000000000"):
        raise ValueError("Le montant dépasse la limite autorisée (1 000 000 000).")

    date_prevue = parse_date(data.get("expected_date"))
    if statut != "Réalisé" and date_prevue is None:
        date_prevue = tx_date  # par defaut, on considere l'echeance = date saisie
    if date_prevue is not None and statut == "Réalisé":
        date_prevue = None

    invoice_id = data.get("invoice_id")
    if invoice_id in ("", 0, "0"):
        invoice_id = None

    return {
        "date": tx_date,
        "type": tx_type,
        "category": _texte(data.get("category"), 60) or "Autres",
        "description": _texte(data.get("description"), 200),
        "amount": finance.money(montant),
        "status": statut,
        "expected_date": date_prevue,
        "party": _texte(data.get("party"), 120),
        "reference": _texte(data.get("reference"), 60),
        "invoice_id": int(invoice_id) if invoice_id not in (None, "") else None,
    }


def validate_invoice(data: dict) -> dict:
    """Valide et normalise une facture. Leve ValueError si invalide."""
    numero = _texte(data.get("number"), 40)
    if not numero:
        raise ValueError("Le numéro de facture est obligatoire.")
    inv_type = _texte(data.get("type"), 20) or "Client"
    if inv_type not in INVOICE_TYPES:
        raise ValueError("Type de facture invalide : 'Client' ou 'Fournisseur'.")
    tiers = _texte(data.get("party"), 120)
    if not tiers:
        raise ValueError("Le nom du client ou du fournisseur est obligatoire.")
    issue = parse_date(data.get("issue_date")) or date.today()
    due = parse_date(data.get("due_date"))
    if due is not None and due < issue:
        raise ValueError("La date d'échéance ne peut pas précéder la date d'émission.")
    total = finance.to_decimal(data.get("total"))
    if total <= 0:
        raise ValueError("Le montant total de la facture doit être supérieur à 0.")
    paye = finance.to_decimal(data.get("paid") or 0)
    if paye < 0:
        raise ValueError("Le montant payé ne peut pas être négatif.")
    if paye > total:
        raise ValueError("Le montant payé ne peut pas dépasser le total de la facture.")
    return {
        "number": numero,
        "type": inv_type,
        "party": tiers,
        "issue_date": issue,
        "due_date": due,
        "total": finance.money(total),
        "paid": finance.money(paye),
        "notes": _texte(data.get("notes"), 300),
    }


# ---------------------------------------------------------------------------
# Factures : lecture
# ---------------------------------------------------------------------------
def _invoice_from_row(row: sqlite3.Row) -> dict:
    inv = {
        "id": row["id"],
        "number": row["invoice_number"],
        "type": row["invoice_type"],
        "party": row["party"],
        "issue_date": parse_date(row["issue_date"]),
        "due_date": parse_date(row["due_date"]),
        "total": float(row["total_amount"]),
        "paid": float(row["amount_paid"]),
        "status": row["status"],
        "notes": row["notes"] or "",
    }
    inv["remaining"] = finance.invoice_remaining(inv)
    return inv


def list_invoices(
    conn: sqlite3.Connection,
    inv_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    only_unpaid: bool = False,
) -> list[dict]:
    requete = "SELECT * FROM invoices WHERE 1 = 1"
    params: list[Any] = []
    if inv_type:
        requete += " AND invoice_type = ?"
        params.append(inv_type)
    if only_unpaid:
        requete += " AND total_amount - amount_paid > 0.005"
    if search:
        requete += " AND (invoice_number LIKE ? OR party LIKE ?)"
        motif = f"%{search.strip()}%"
        params.extend([motif, motif])
    requete += " ORDER BY due_date IS NULL, due_date ASC, id DESC"
    factures = [_invoice_from_row(r) for r in conn.execute(requete, params).fetchall()]
    if status:
        today = date.today()
        factures = [f for f in factures if finance.compute_invoice_status(f, today) == status]
    return factures


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> Optional[dict]:
    ligne = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    return _invoice_from_row(ligne) if ligne else None


def next_invoice_number(conn: sqlite3.Connection, inv_type: str, year: Optional[int] = None) -> str:
    annee = year or date.today().year
    prefixe = "FA" if inv_type == "Client" else "FF"
    motif = f"{prefixe}-{annee}-%"
    lignes = conn.execute(
        "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?", (motif,)
    ).fetchall()
    maximum = 0
    for ligne in lignes:
        try:
            maximum = max(maximum, int(str(ligne["invoice_number"]).split("-")[-1]))
        except (ValueError, IndexError):
            continue
    return f"{prefixe}-{annee}-{maximum + 1:04d}"


def add_invoice(conn: sqlite3.Connection, data: dict) -> int:
    inv = validate_invoice(data)
    deja = conn.execute(
        "SELECT id FROM invoices WHERE invoice_number = ?", (inv["number"],)
    ).fetchone()
    if deja:
        raise ValueError(f"Le numéro de facture {inv['number']} existe déjà.")
    statut = finance.compute_invoice_status(inv, date.today())
    with conn:
        curseur = conn.execute(
            """INSERT INTO invoices
               (invoice_number, invoice_type, party, issue_date, due_date,
                total_amount, amount_paid, status, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                inv["number"],
                inv["type"],
                inv["party"],
                fmt_date(inv["issue_date"]),
                fmt_date(inv["due_date"]),
                inv["total"],
                inv["paid"],
                statut,
                inv["notes"],
                _now(),
            ),
        )
    return int(curseur.lastrowid)


def update_invoice(conn: sqlite3.Connection, invoice_id: int, data: dict) -> None:
    existante = get_invoice(conn, invoice_id)
    if existante is None:
        raise ValueError("Facture introuvable.")
    inv = validate_invoice(data)
    doublon = conn.execute(
        "SELECT id FROM invoices WHERE invoice_number = ? AND id <> ?",
        (inv["number"], invoice_id),
    ).fetchone()
    if doublon:
        raise ValueError(f"Le numéro de facture {inv['number']} existe déjà.")
    statut = finance.compute_invoice_status(inv, date.today())
    with conn:
        conn.execute(
            """UPDATE invoices
               SET invoice_number = ?, invoice_type = ?, party = ?, issue_date = ?,
                   due_date = ?, total_amount = ?, amount_paid = ?, status = ?, notes = ?
               WHERE id = ?""",
            (
                inv["number"],
                inv["type"],
                inv["party"],
                fmt_date(inv["issue_date"]),
                fmt_date(inv["due_date"]),
                inv["total"],
                inv["paid"],
                statut,
                inv["notes"],
                invoice_id,
            ),
        )


def delete_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict:
    """Supprime une facture, ses paiements et les transactions qui lui sont liees."""
    existante = get_invoice(conn, invoice_id)
    if existante is None:
        raise ValueError("Facture introuvable.")
    with conn:
        liees = conn.execute(
            "SELECT id FROM transactions WHERE invoice_id = ?", (invoice_id,)
        ).fetchall()
        conn.execute("DELETE FROM transactions WHERE invoice_id = ?", (invoice_id,))
        conn.execute("DELETE FROM payments WHERE invoice_id = ?", (invoice_id,))
        conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    return {"invoice": existante["number"], "linked_transactions": len(liees)}


# ---------------------------------------------------------------------------
# Transactions : lecture
# ---------------------------------------------------------------------------
def _tx_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "date": parse_date(row["tx_date"]),
        "type": row["tx_type"],
        "category": row["category"],
        "description": row["description"] or "",
        "amount": float(row["amount"]),
        "status": row["status"],
        "expected_date": parse_date(row["expected_date"]),
        "party": row["party"] or "",
        "reference": row["reference"] or "",
        "invoice_id": row["invoice_id"],
    }


def list_transactions(
    conn: sqlite3.Connection,
    start: Optional[date] = None,
    end: Optional[date] = None,
    tx_type: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    requete = "SELECT * FROM transactions WHERE 1 = 1"
    params: list[Any] = []
    if start is not None:
        requete += " AND tx_date >= ?"
        params.append(fmt_date(start))
    if end is not None:
        requete += " AND tx_date <= ?"
        params.append(fmt_date(end))
    if tx_type:
        requete += " AND tx_type = ?"
        params.append(tx_type)
    if status:
        requete += " AND status = ?"
        params.append(status)
    if category:
        requete += " AND category = ?"
        params.append(category)
    if search:
        requete += (
            " AND (description LIKE ? OR party LIKE ? OR reference LIKE ?"
            " OR category LIKE ?)"
        )
        motif = f"%{search.strip()}%"
        params.extend([motif, motif, motif, motif])
    requete += " ORDER BY tx_date DESC, id DESC"
    if limit:
        requete += " LIMIT ?"
        params.append(int(limit))
    return [_tx_from_row(r) for r in conn.execute(requete, params).fetchall()]


def get_transaction(conn: sqlite3.Connection, tx_id: int) -> Optional[dict]:
    ligne = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    return _tx_from_row(ligne) if ligne else None


def _insert_transaction(conn: sqlite3.Connection, tx: dict) -> int:
    curseur = conn.execute(
        """INSERT INTO transactions
           (tx_date, tx_type, category, description, amount, status,
            expected_date, party, reference, invoice_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            fmt_date(tx["date"]),
            tx["type"],
            tx["category"],
            tx["description"],
            tx["amount"],
            tx["status"],
            fmt_date(tx["expected_date"]),
            tx["party"],
            tx["reference"],
            tx["invoice_id"],
            _now(),
        ),
    )
    return int(curseur.lastrowid)


def add_transaction(conn: sqlite3.Connection, data: dict) -> int:
    tx = validate_transaction(data)
    with conn:
        return _insert_transaction(conn, tx)


def add_transactions_bulk(conn: sqlite3.Connection, lignes: Iterable[dict]) -> int:
    """Insertion groupee (import CSV / Excel) : tout ou rien."""
    valides = [validate_transaction(ligne) for ligne in lignes]
    if not valides:
        return 0
    with conn:
        for tx in valides:
            _insert_transaction(conn, tx)
    return len(valides)


def update_transaction(conn: sqlite3.Connection, tx_id: int, data: dict) -> None:
    existante = get_transaction(conn, tx_id)
    if existante is None:
        raise ValueError("Transaction introuvable.")
    tx = validate_transaction(data)
    if existante.get("invoice_id"):
        modifie_le_montant = abs(
            finance.to_decimal(tx["amount"]) - finance.to_decimal(existante["amount"])
        ) > finance.TOLERANCE
        if modifie_le_montant or tx["date"] != existante["date"]:
            raise ValueError(
                "Cette opération est le règlement d'une facture : son montant et sa date "
                "ne peuvent pas être modifiés ici. Supprimez le règlement depuis la page "
                "Factures, puis enregistrez-le à nouveau."
            )
    with conn:
        conn.execute(
            """UPDATE transactions
               SET tx_date = ?, tx_type = ?, category = ?, description = ?,
                   amount = ?, status = ?, expected_date = ?, party = ?,
                   reference = ?, invoice_id = ?
               WHERE id = ?""",
            (
                fmt_date(tx["date"]),
                tx["type"],
                tx["category"],
                tx["description"],
                tx["amount"],
                tx["status"],
                fmt_date(tx["expected_date"]),
                tx["party"],
                tx["reference"],
                tx["invoice_id"],
                tx_id,
            ),
        )


def delete_transaction(conn: sqlite3.Connection, tx_id: int) -> dict:
    """Supprime une transaction.

    Si la transaction est le reglement d'une facture, le paiement correspondant
    est supprime et le solde de la facture est recalcule : les deux restent
    toujours coherents.
    """
    transaction = get_transaction(conn, tx_id)
    if transaction is None:
        raise ValueError("Transaction introuvable.")
    info = {"invoice_updated": False, "invoice_number": None}
    with conn:
        if transaction.get("invoice_id"):
            paiement = conn.execute(
                "SELECT * FROM payments WHERE transaction_id = ?", (tx_id,)
            ).fetchone()
            if paiement is not None:
                conn.execute("DELETE FROM payments WHERE id = ?", (paiement["id"],))
                ligne = conn.execute(
                    "SELECT * FROM invoices WHERE id = ?", (transaction["invoice_id"],)
                ).fetchone()
                if ligne is not None:
                    facture = _invoice_from_row(ligne)
                    nouveau_paye = max(
                        finance.to_decimal(0),
                        finance.to_decimal(facture["paid"]) - finance.to_decimal(paiement["amount"]),
                    )
                    mise_a_jour = dict(facture)
                    mise_a_jour["paid"] = nouveau_paye
                    statut = finance.compute_invoice_status(mise_a_jour, date.today())
                    conn.execute(
                        "UPDATE invoices SET amount_paid = ?, status = ? WHERE id = ?",
                        (finance.money(nouveau_paye), statut, transaction["invoice_id"]),
                    )
                    info["invoice_updated"] = True
                    info["invoice_number"] = facture["number"]
        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    return info


def refresh_transaction_statuses(
    conn: sqlite3.Connection, today: Optional[date] = None
) -> int:
    """Marque 'En retard' les operations prevues dont l'echeance est depassee."""
    today = today or date.today()
    curseur = conn.execute(
        """UPDATE transactions SET status = 'En retard'
           WHERE status = 'Prévu'
             AND COALESCE(expected_date, tx_date) < ?""",
        (fmt_date(today),),
    )
    conn.commit()
    return curseur.rowcount


# ---------------------------------------------------------------------------
# Paiements de factures (operation atomique)
# ---------------------------------------------------------------------------
def record_payment(
    conn: sqlite3.Connection,
    invoice_id: int,
    amount: Any,
    payment_date: Optional[Any] = None,
    note: str = "",
) -> dict:
    """Enregistre un reglement de facture de facon atomique.

    1. Valide le montant (positif, <= solde restant).
    2. Refuse un paiement strictement identique deja enregistre.
    3. Cree UNE transaction realisee liee a la facture.
    4. Met a jour le solde et le statut de la facture.

    En cas d'erreur, aucune des etapes n'est conservee (rollback).
    """
    montant = finance.to_decimal(amount)
    if montant <= 0:
        raise ValueError("Le montant du paiement doit être strictement supérieur à 0.")
    date_paiement = parse_date(payment_date) or date.today()
    if date_paiement > date.today():
        raise ValueError("La date du paiement ne peut pas être dans le futur.")

    with conn:  # transaction SQLite : commit si tout reussit, rollback sinon
        ligne = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if ligne is None:
            raise ValueError("Facture introuvable.")
        facture = _invoice_from_row(ligne)
        reste = finance.to_decimal(facture["remaining"])
        if reste <= finance.TOLERANCE:
            raise ValueError(
                f"La facture {facture['number']} est déjà entièrement payée."
            )
        if montant - reste > finance.TOLERANCE:
            raise ValueError(
                f"Surpaiement refusé : solde restant de {finance.money_str(reste)} "
                f"(paiement demandé : {finance.money_str(montant)})."
            )

        doublon = conn.execute(
            """SELECT id FROM payments
               WHERE invoice_id = ? AND payment_date = ? AND amount = ?""",
            (invoice_id, fmt_date(date_paiement), finance.money(montant)),
        ).fetchone()
        if doublon:
            raise ValueError(
                "Un paiement d'un montant identique a déjà été enregistré pour cette "
                "facture à cette date : doublon bloqué."
            )

        entree = facture["type"] == "Client"
        tx_id = _insert_transaction(
            conn,
            {
                "date": date_paiement,
                "type": "Encaissement" if entree else "Décaissement",
                "category": "Ventes" if entree else "Achats",
                "description": (
                    f"Règlement {'client' if entree else 'fournisseur'} "
                    f"facture {facture['number']}"
                ),
                "amount": finance.money(montant),
                "status": "Réalisé",
                "expected_date": None,
                "party": facture["party"],
                "reference": facture["number"],
                "invoice_id": invoice_id,
            },
        )

        conn.execute(
            """INSERT INTO payments
               (invoice_id, payment_date, amount, transaction_id, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                invoice_id,
                fmt_date(date_paiement),
                finance.money(montant),
                tx_id,
                _texte(note, 200),
                _now(),
            ),
        )

        nouveau_paye = finance.to_decimal(facture["paid"]) + montant
        mise_a_jour = {
            "total": facture["total"],
            "paid": finance.money(nouveau_paye),
            "due_date": facture["due_date"],
        }
        statut = finance.compute_invoice_status(mise_a_jour, date.today())
        conn.execute(
            "UPDATE invoices SET amount_paid = ?, status = ? WHERE id = ?",
            (finance.money(nouveau_paye), statut, invoice_id),
        )

    return {
        "invoice_id": invoice_id,
        "invoice_number": facture["number"],
        "amount": finance.money(montant),
        "date": date_paiement,
        "transaction_id": tx_id,
        "new_status": statut,
        "remaining": finance.invoice_remaining(
            {"total": facture["total"], "paid": finance.money(nouveau_paye)}
        ),
    }


def list_payments(conn: sqlite3.Connection, invoice_id: Optional[int] = None) -> list[dict]:
    requete = """SELECT p.*, i.invoice_number, i.invoice_type, i.party
                 FROM payments p JOIN invoices i ON i.id = p.invoice_id"""
    params: list[Any] = []
    if invoice_id:
        requete += " WHERE p.invoice_id = ?"
        params.append(invoice_id)
    requete += " ORDER BY p.payment_date DESC, p.id DESC"
    resultat = []
    for ligne in conn.execute(requete, params).fetchall():
        resultat.append(
            {
                "id": ligne["id"],
                "invoice_id": ligne["invoice_id"],
                "invoice_number": ligne["invoice_number"],
                "type": ligne["invoice_type"],
                "party": ligne["party"],
                "date": parse_date(ligne["payment_date"]),
                "amount": float(ligne["amount"]),
                "transaction_id": ligne["transaction_id"],
                "note": ligne["note"] or "",
            }
        )
    return resultat


def refresh_invoice_statuses(conn: sqlite3.Connection, today: Optional[date] = None) -> None:
    """Recalcule les statuts stockes (appele a chaque lancement de l'application)."""
    today = today or date.today()
    factures = [_invoice_from_row(r) for r in conn.execute("SELECT * FROM invoices").fetchall()]
    with conn:
        for facture in factures:
            statut = finance.compute_invoice_status(facture, today)
            if statut != facture["status"]:
                conn.execute(
                    "UPDATE invoices SET status = ? WHERE id = ?", (statut, facture["id"])
                )


# ---------------------------------------------------------------------------
# Chargement / reinitialisation
# ---------------------------------------------------------------------------
def clear_all_data(conn: sqlite3.Connection) -> None:
    """Vide transactions, factures et paiements (les parametres sont conserves)."""
    with conn:
        conn.execute("DELETE FROM payments")
        conn.execute("DELETE FROM transactions")
        conn.execute("DELETE FROM invoices")
    conn.execute("VACUUM")


def reset_settings(conn: sqlite3.Connection) -> dict:
    return update_settings(
        conn,
        company_name=DEFAULT_SETTINGS["company_name"],
        currency=DEFAULT_SETTINGS["currency"],
        opening_cash=0.0,
        opening_cash_date=date.today(),
        min_cash_threshold=0.0,
        demo_mode=0,
    )


def database_stats(conn: sqlite3.Connection) -> dict:
    nb_tx = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]
    nb_factures = conn.execute("SELECT COUNT(*) AS n FROM invoices").fetchone()["n"]
    nb_paiements = conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
    return {
        "transactions": int(nb_tx),
        "invoices": int(nb_factures),
        "payments": int(nb_paiements),
        "path": str(DB_PATH),
    }
