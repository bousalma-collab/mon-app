"""Import / export de fichiers (CSV, Excel, PDF) pour CashFlow AI."""

from __future__ import annotations

import io
from datetime import date
from typing import Any, Iterable, Optional

import pandas as pd

import db
import finance

try:  # PDF optionnel : l'export CSV / Excel reste toujours disponible
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    HAS_REPORTLAB = True
except Exception:  # noqa: BLE001
    HAS_REPORTLAB = False


TRANSACTION_COLONNES = [
    ("id", "ID"),
    ("date", "Date"),
    ("type", "Type"),
    ("category", "Catégorie"),
    ("description", "Description"),
    ("amount", "Montant (MAD)"),
    ("status", "Statut"),
    ("expected_date", "Date prévue"),
    ("party", "Tiers"),
    ("reference", "Référence"),
]

INVOICE_COLONNES = [
    ("number", "N° facture"),
    ("type", "Type"),
    ("party", "Tiers"),
    ("issue_date", "Émission"),
    ("due_date", "Échéance"),
    ("total", "Total (MAD)"),
    ("paid", "Payé (MAD)"),
    ("remaining", "Restant (MAD)"),
    ("status", "Statut"),
]


# ---------------------------------------------------------------------------
# DataFrames d'affichage
# ---------------------------------------------------------------------------
def transactions_dataframe(transactions: Iterable[dict]) -> pd.DataFrame:
    lignes = []
    for tx in transactions:
        lignes.append(
            {
                "ID": tx.get("id"),
                "Date": tx.get("date"),
                "Type": tx.get("type"),
                "Catégorie": tx.get("category"),
                "Description": tx.get("description"),
                "Montant (MAD)": tx.get("amount"),
                "Signe": "+" if tx.get("type") == "Encaissement" else "-",
                "Statut": tx.get("status"),
                "Date prévue": tx.get("expected_date"),
                "Tiers": tx.get("party"),
                "Référence": tx.get("reference"),
                "Facture liée": tx.get("invoice_id"),
            }
        )
    colonnes = [
        "ID", "Date", "Type", "Catégorie", "Description", "Montant (MAD)",
        "Signe", "Statut", "Date prévue", "Tiers", "Référence", "Facture liée",
    ]
    return pd.DataFrame(lignes, columns=colonnes)


def invoices_dataframe(invoices: Iterable[dict], today: Optional[date] = None) -> pd.DataFrame:
    today = today or date.today()
    lignes = []
    for inv in invoices:
        lignes.append(
            {
                "N° facture": inv.get("number"),
                "Type": inv.get("type"),
                "Tiers": inv.get("party"),
                "Émission": inv.get("issue_date"),
                "Échéance": inv.get("due_date"),
                "Total (MAD)": inv.get("total"),
                "Payé (MAD)": inv.get("paid"),
                "Restant (MAD)": finance.invoice_remaining(inv),
                "Statut": finance.compute_invoice_status(inv, today),
                "Retard (jours)": finance.overdue_days(inv, today),
            }
        )
    colonnes = [
        "N° facture", "Type", "Tiers", "Émission", "Échéance", "Total (MAD)",
        "Payé (MAD)", "Restant (MAD)", "Statut", "Retard (jours)",
    ]
    return pd.DataFrame(lignes, columns=colonnes)


def payments_dataframe(payments: Iterable[dict]) -> pd.DataFrame:
    lignes = []
    for p in payments:
        lignes.append(
            {
                "Date": p.get("date"),
                "Facture": p.get("invoice_number"),
                "Type": p.get("type"),
                "Tiers": p.get("party"),
                "Montant (MAD)": p.get("amount"),
                "Transaction liée": p.get("transaction_id"),
                "Note": p.get("note"),
            }
        )
    return pd.DataFrame(
        lignes,
        columns=["Date", "Facture", "Type", "Tiers", "Montant (MAD)", "Transaction liée", "Note"],
    )


def forecast_dataframe(forecast: dict) -> pd.DataFrame:
    lignes = []
    for jour in forecast.get("days", []):
        lignes.append(
            {
                "Date": jour["date"],
                "Encaissements (MAD)": jour["inflows"],
                "Décaissements (MAD)": jour["outflows"],
                "Flux net (MAD)": jour["net"],
                "Trésorerie projetée (MAD)": jour["closing"],
                "Sous le seuil": "Oui" if jour["below_threshold"] else "Non",
            }
        )
    return pd.DataFrame(
        lignes,
        columns=[
            "Date", "Encaissements (MAD)", "Décaissements (MAD)", "Flux net (MAD)",
            "Trésorerie projetée (MAD)", "Sous le seuil",
        ],
    )


def forecast_items_dataframe(items: Iterable[dict]) -> pd.DataFrame:
    lignes = []
    for it in items:
        lignes.append(
            {
                "Date prévue": it.get("date"),
                "Sens": "Encaissement" if it.get("direction") == "in" else "Décaissement",
                "Libellé": it.get("label"),
                "Tiers": it.get("party"),
                "Catégorie": it.get("category"),
                "Montant (MAD)": it.get("amount"),
                "Origine": "Transaction prévue" if it.get("source") == "transaction" else "Facture",
                "Statut": it.get("status"),
                "Déjà en retard": "Oui" if it.get("overdue") else "Non",
            }
        )
    return pd.DataFrame(
        lignes,
        columns=[
            "Date prévue", "Sens", "Libellé", "Tiers", "Catégorie", "Montant (MAD)",
            "Origine", "Statut", "Déjà en retard",
        ],
    )


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """CSV compatible Excel francais (separateur ';', encodage UTF-8 BOM)."""
    return df.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig").encode("utf-8-sig")


def to_excel_bytes(feuilles: dict[str, pd.DataFrame]) -> bytes:
    """Classeur Excel multi-feuilles."""
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as writer:
        for nom, df in feuilles.items():
            nom_propre = str(nom)[:31]
            df.to_excel(writer, sheet_name=nom_propre, index=False)
            feuille = writer.sheets[nom_propre]
            for index, colonne in enumerate(df.columns, start=1):
                largeur = max(
                    len(str(colonne)) + 2,
                    *(len(str(v)) + 2 for v in df[colonne].head(200)) if len(df) else [12],
                )
                feuille.column_dimensions[
                    feuille.cell(row=1, column=index).column_letter
                ].width = min(45, max(10, largeur))
    tampon.seek(0)
    return tampon.read()


def csv_template_bytes() -> bytes:
    modele = pd.DataFrame(
        [
            {
                "date": date.today().isoformat(),
                "type": "Encaissement",
                "categorie": "Ventes",
                "description": "Reglement client exemple",
                "montant": "15000,00",
                "statut": "Réalisé",
                "date_prevue": "",
                "tiers": "Client Exemple SA",
                "reference": "FAC-0001",
            },
            {
                "date": date.today().isoformat(),
                "type": "Décaissement",
                "categorie": "Achats",
                "description": "Achat marchandises prevu",
                "montant": "8000,00",
                "statut": "Prévu",
                "date_prevue": (date.today()).isoformat(),
                "tiers": "Fournisseur Exemple",
                "reference": "CMD-0007",
            },
        ]
    )
    return modele.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def pdf_report_bytes(company: str, sections: dict[str, Any]) -> Optional[bytes]:
    """Rapport PDF simple (necesite reportlab). Renvoie None si indisponible."""
    if not HAS_REPORTLAB:
        return None
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(
        tampon,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"Rapport de tresorerie - {company}",
        author="CashFlow AI",
    )
    styles = getSampleStyleSheet()
    titre = ParagraphStyle(
        "TitreCF", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#0f2038")
    )
    sous_titre = ParagraphStyle(
        "SousCF", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#5b6b82")
    )
    h2 = ParagraphStyle(
        "H2CF",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#0f2038"),
        spaceBefore=10,
        spaceAfter=4,
    )
    normal = ParagraphStyle("NormCF", parent=styles["Normal"], fontSize=9)

    elements: list[Any] = [
        Paragraph("Rapport de trésorerie", titre),
        Paragraph(f"{company} — CashFlow AI", sous_titre),
    ]
    for titre_section, contenu in sections.items():
        elements.append(Paragraph(str(titre_section), h2))
        if isinstance(contenu, pd.DataFrame) and not contenu.empty:
            donnees = [list(contenu.columns)] + contenu.astype(str).values.tolist()
            tableau = Table(donnees, repeatRows=1, hAlign="LEFT")
            tableau.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2038")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c9d3e0")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6fb")]),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )
            elements.append(tableau)
        elif isinstance(contenu, (list, tuple)) and contenu:
            donnees = [["Indicateur", "Valeur"]] + [[str(a), str(b)] for a, b in contenu]
            tableau = Table(donnees, repeatRows=1, hAlign="LEFT")
            tableau.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2038")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c9d3e0")),
                    ]
                )
            )
            elements.append(tableau)
        else:
            texte = str(contenu).replace("\n", "<br/>")
            elements.append(Paragraph(texte or "Aucune donnée.", normal))
        elements.append(Spacer(1, 6))
    elements.append(
        Paragraph(
            "Document généré par CashFlow AI — les montants prévisionnels sont des "
            "estimations, pas des certitudes.",
            sous_titre,
        )
    )
    doc.build(elements)
    tampon.seek(0)
    return tampon.read()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
ALIAS_COLONNES = {
    "date": "date",
    "date operation": "date",
    "date_operation": "date",
    "date de loperation": "date",
    "type": "type",
    "sens": "type",
    "categorie": "category",
    "catégorie": "category",
    "category": "category",
    "description": "description",
    "libelle": "description",
    "libellé": "description",
    "montant": "amount",
    "montant (mad)": "amount",
    "amount": "amount",
    "somme": "amount",
    "statut": "status",
    "status": "status",
    "etat": "status",
    "date prevue": "expected_date",
    "date prévue": "expected_date",
    "date_prevue": "expected_date",
    "echeance": "expected_date",
    "échéance": "expected_date",
    "tiers": "party",
    "party": "party",
    "client": "party",
    "fournisseur": "party",
    "reference": "reference",
    "référence": "reference",
    "ref": "reference",
}

TYPE_ALIAS = {
    "encaissement": "Encaissement",
    "entree": "Encaissement",
    "entrée": "Encaissement",
    "recette": "Encaissement",
    "in": "Encaissement",
    "credit": "Encaissement",
    "crédit": "Encaissement",
    "decaissement": "Décaissement",
    "décaissement": "Décaissement",
    "sortie": "Décaissement",
    "depense": "Décaissement",
    "dépense": "Décaissement",
    "out": "Décaissement",
    "debit": "Décaissement",
    "débit": "Décaissement",
}

STATUT_ALIAS = {
    "realise": "Réalisé",
    "réalisé": "Réalisé",
    "effectue": "Réalisé",
    "effectué": "Réalisé",
    "paye": "Réalisé",
    "payé": "Réalisé",
    "prevu": "Prévu",
    "prévu": "Prévu",
    "planifie": "Prévu",
    "planifié": "Prévu",
    "a venir": "Prévu",
    "en retard": "En retard",
    "retard": "En retard",
    "impaye": "En retard",
    "impayé": "En retard",
}


def _normaliser_colonnes(df: pd.DataFrame) -> pd.DataFrame:
    correspondance = {}
    for colonne in df.columns:
        cle = str(colonne).strip().lower()
        if cle in ALIAS_COLONNES:
            correspondance[colonne] = ALIAS_COLONNES[cle]
    return df.rename(columns=correspondance)


def _montant_nettoye(valeur: Any) -> Any:
    if valeur is None or valeur == "":
        return valeur
    texte = str(valeur)
    for parasite in ("MAD", "mad", "Dh", "dh", "Dhs", "€", "$"):
        texte = texte.replace(parasite, "")
    return texte.strip()


def lire_fichier_transactions(file_like: Any, nom_fichier: str = "") -> tuple[list[dict], list[str]]:
    """Lit un CSV ou Excel et renvoie (transactions valides, erreurs lisibles)."""
    nom = (nom_fichier or getattr(file_like, "name", "") or "").lower()
    if nom.endswith((".xlsx", ".xls", ".xlsm")):
        df = pd.read_excel(file_like)
    else:
        donnees = file_like.read() if hasattr(file_like, "read") else file_like
        texte: Optional[str] = None
        for encodage in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                texte = donnees.decode(encodage)
                break
            except (UnicodeDecodeError, AttributeError):
                continue
        if texte is None:
            raise ValueError("Impossible de lire le fichier (encodage non reconnu).")
        separateur = ";" if texte.count(";") >= texte.count(",") else ","
        df = pd.read_csv(io.StringIO(texte), sep=separateur, dtype=str)

    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("Le fichier ne contient aucune ligne de données.")
    df = _normaliser_colonnes(df)
    colonnes_connues = set(df.columns) & {
        "date", "type", "category", "description", "amount", "status",
        "expected_date", "party", "reference",
    }
    if "date" not in colonnes_connues or "amount" not in colonnes_connues:
        raise ValueError(
            "Colonnes obligatoires manquantes : le fichier doit contenir au minimum "
            "les colonnes 'date' et 'montant'."
        )

    lignes: list[dict] = []
    erreurs: list[str] = []
    for position, (_, ligne) in enumerate(df.iterrows(), start=2):
        brut = ligne.to_dict()
        try:
            type_brut = str(brut.get("type") or "Encaissement").strip().lower()
            tx_type = TYPE_ALIAS.get(type_brut, str(brut.get("type") or "").strip())
            statut_brut = str(brut.get("status") or "Réalisé").strip().lower()
            statut = STATUT_ALIAS.get(statut_brut, str(brut.get("status") or "").strip())
            candidat = {
                "date": brut.get("date"),
                "type": tx_type,
                "category": brut.get("category") or "Autres",
                "description": brut.get("description") or "",
                "amount": _montant_nettoye(brut.get("amount")),
                "status": statut,
                "expected_date": brut.get("expected_date"),
                "party": brut.get("party") or "",
                "reference": brut.get("reference") or "",
            }
            if pd.isna(candidat["expected_date"]):
                candidat["expected_date"] = None
            lignes.append(db.validate_transaction(candidat))
        except ValueError as exc:
            erreurs.append(f"Ligne {position} ignorée : {exc}")
        except Exception as exc:  # noqa: BLE001
            erreurs.append(f"Ligne {position} ignorée : {exc}")
    return lignes, erreurs
