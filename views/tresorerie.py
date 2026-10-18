"""Page « Trésorerie » : gestion des transactions (CRUD, filtres, import/export)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db
import finance
import io_utils
import theme


def _filtres(ctx: dict) -> dict:
    today = ctx["today"]
    colonnes = st.columns([2, 1.6, 1.2, 1.2, 1.4])
    with colonnes[0]:
        recherche = st.text_input(
            "Recherche", placeholder="Description, tiers, référence…", key="tx_recherche"
        )
    with colonnes[1]:
        periode = st.date_input(
            "Période (date de l'opération)",
            value=(today - timedelta(days=120), today),
            key="tx_periode",
        )
    with colonnes[2]:
        tx_type = st.selectbox(
            "Type", ["Tous", "Encaissement", "Décaissement"], key="tx_type"
        )
    with colonnes[3]:
        statut = st.selectbox(
            "Statut", ["Tous", *finance.TRANSACTION_STATUSES], key="tx_statut"
        )
    with colonnes[4]:
        categorie = st.selectbox(
            "Catégorie", ["Toutes", *finance.CATEGORIES_DEFAUT], key="tx_categorie"
        )

    if isinstance(periode, (tuple, list)):
        debut, fin = (periode[0], periode[-1])
    else:
        debut, fin = periode, periode
    return {
        "search": recherche.strip() or None,
        "start": debut,
        "end": fin,
        "type": None if tx_type == "Tous" else tx_type,
        "status": None if statut == "Tous" else statut,
        "category": None if categorie == "Toutes" else categorie,
    }


def _formulaire(prefixe: str, valeurs: dict, soumettre: str) -> tuple[dict, bool]:
    """Formulaire de saisie d'une transaction (creation ou modification)."""
    with st.form(key=f"form_{prefixe}", clear_on_submit=False):
        colonnes = st.columns(2)
        with colonnes[0]:
            date_tx = st.date_input(
                "Date de l'opération *", value=valeurs["date"], key=f"{prefixe}_date"
            )
            tx_type = st.selectbox(
                "Type *",
                list(finance.TRANSACTION_TYPES),
                index=list(finance.TRANSACTION_TYPES).index(valeurs["type"]),
                key=f"{prefixe}_type",
            )
            categorie = st.selectbox(
                "Catégorie *",
                list(finance.CATEGORIES_DEFAUT),
                index=(
                    list(finance.CATEGORIES_DEFAUT).index(valeurs["category"])
                    if valeurs["category"] in finance.CATEGORIES_DEFAUT
                    else len(finance.CATEGORIES_DEFAUT) - 1
                ),
                key=f"{prefixe}_categorie",
            )
            montant = st.number_input(
                "Montant (MAD) *",
                min_value=0.0,
                value=float(valeurs["amount"]),
                step=100.0,
                format="%.2f",
                key=f"{prefixe}_montant",
            )
            description = st.text_input(
                "Description", value=valeurs["description"], key=f"{prefixe}_description"
            )
        with colonnes[1]:
            statut = st.selectbox(
                "Statut *",
                list(finance.TRANSACTION_STATUSES),
                index=list(finance.TRANSACTION_STATUSES).index(valeurs["status"]),
                key=f"{prefixe}_statut",
                help=(
                    "« Réalisé » = mouvement de trésorerie effectif. "
                    "« Prévu » / « En retard » = attendu, compte uniquement en prévision."
                ),
            )
            date_prevue = st.date_input(
                "Date prévue de règlement",
                value=valeurs["expected_date"] or valeurs["date"],
                key=f"{prefixe}_date_prevue",
                help="Utilisée pour placer l'opération dans la prévision de trésorerie.",
            )
            tiers = st.text_input(
                "Client ou fournisseur", value=valeurs["party"], key=f"{prefixe}_tiers"
            )
            reference = st.text_input(
                "Référence (facture, commande…)",
                value=valeurs["reference"],
                key=f"{prefixe}_reference",
            )
            st.caption(
                "Les champs marqués * sont obligatoires. Le montant doit être strictement "
                "positif ; le sens est donné par le type."
            )
        valider = st.form_submit_button(soumettre)
    return (
        {
            "date": date_tx,
            "type": tx_type,
            "category": categorie,
            "description": description,
            "amount": montant,
            "status": statut,
            "expected_date": None if statut == "Réalisé" else date_prevue,
            "party": tiers,
            "reference": reference,
        },
        valider,
    )


def render(ctx: dict) -> None:
    conn = ctx["conn"]
    settings = ctx["settings"]
    devise = settings.get("currency") or "MAD"
    today = ctx["today"]
    transactions = ctx["transactions"]

    theme.page_title(
        "Trésorerie",
        "Saisie, suivi et contrôle des encaissements et décaissements (réels et prévus).",
    )
    theme.demo_banner(bool(settings.get("demo_mode")), settings.get("company_name", ""))

    filtres = _filtres(ctx)
    filtrees = db.list_transactions(
        conn,
        start=filtres["start"],
        end=filtres["end"],
        tx_type=filtres["type"],
        status=filtres["status"],
        category=filtres["category"],
        search=filtres["search"],
    )

    totaux = finance.cash_totals(filtrees, filtres["start"], filtres["end"])
    encaisse_prevu = sum(
        finance.to_decimal(tx["amount"])
        for tx in filtrees
        if not finance.is_actual(tx) and tx["type"] == "Encaissement"
    )
    decaisse_prevu = sum(
        finance.to_decimal(tx["amount"])
        for tx in filtrees
        if not finance.is_actual(tx) and tx["type"] == "Décaissement"
    )

    theme.kpi_row(
        [
            {
                "label": "Trésorerie actuelle (globale)",
                "value": finance.money_str(finance.actual_cash(settings, transactions), devise),
                "sub": "Toutes périodes confondues",
                "tone": "positive",
            },
            {
                "label": "Encaissements réalisés (période)",
                "value": finance.money_str(totaux["inflows"], devise),
                "sub": f"{len([t for t in filtrees if finance.is_actual(t)])} opération(s) réalisée(s)",
                "tone": "positive",
            },
            {
                "label": "Décaissements réalisés (période)",
                "value": finance.money_str(totaux["outflows"], devise),
                "sub": "Mouvements effectifs sortants",
                "tone": "danger",
            },
            {
                "label": "Flux net réalisé (période)",
                "value": finance.money_str(totaux["net"], devise),
                "sub": (
                    f"Prévu à venir : entrées {finance.money_str(encaisse_prevu, devise)} / "
                    f"sorties {finance.money_str(decaisse_prevu, devise)}"
                ),
                "tone": "positive" if totaux["net"] >= 0 else "danger",
            },
        ]
    )

    theme.section(f"{len(filtrees)} transaction(s) affichée(s)")
    if filtrees:
        df = io_utils.transactions_dataframe(filtrees)
        affichage = df.drop(columns=["Signe"])
        theme.dataframe(
            theme.style_dataframe(affichage, ["Montant (MAD)"]),
            height=420,
        )
        colonnes_export = st.columns([1, 1, 3])
        with colonnes_export[0]:
            theme.download_button(
                "Exporter en CSV",
                io_utils.to_csv_bytes(df),
                f"transactions_{today.isoformat()}.csv",
                "text/csv",
                "tx_export_csv",
            )
        with colonnes_export[1]:
            theme.download_button(
                "Exporter en Excel",
                io_utils.to_excel_bytes({"Transactions": df}),
                f"transactions_{today.isoformat()}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "tx_export_xlsx",
            )
    else:
        st.info("Aucune transaction ne correspond aux filtres sélectionnés.")

    onglet_ajout, onglet_edition, onglet_import = st.tabs(
        ["Ajouter une transaction", "Modifier ou supprimer", "Importer (CSV / Excel)"]
    )

    # ------------------------------------------------------------- Ajout
    with onglet_ajout:
        valeurs = {
            "date": today,
            "type": "Encaissement",
            "category": "Ventes",
            "description": "",
            "amount": 0.0,
            "status": "Réalisé",
            "expected_date": today,
            "party": "",
            "reference": "",
        }
        donnees, valider = _formulaire("creer", valeurs, "Enregistrer la transaction")
        if valider:
            try:
                identifiant = db.add_transaction(conn, donnees)
                st.success(
                    f"Transaction n°{identifiant} enregistrée : "
                    f"{donnees['type']} de {finance.money_str(donnees['amount'], devise)}."
                )
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    # ---------------------------------------------------------- Edition
    with onglet_edition:
        if not transactions:
            st.info("Aucune transaction à modifier.")
        else:
            options = [tx["id"] for tx in transactions]

            def _etiquette(identifiant: int) -> str:
                tx = next((t for t in transactions if t["id"] == identifiant), None)
                if tx is None:
                    return str(identifiant)
                return (
                    f"#{tx['id']} — {finance.format_date_fr(tx['date'])} — {tx['type']} — "
                    f"{finance.money_str(tx['amount'], devise)} — {tx['status']} — "
                    f"{tx['description'][:40]}"
                )

            selection = st.selectbox(
                "Transaction à modifier", options, format_func=_etiquette, key="tx_edition_id"
            )
            courante = next((t for t in transactions if t["id"] == selection), None)
            if courante is not None:
                if courante.get("invoice_id"):
                    st.warning(
                        f"Cette opération est le règlement de la facture liée (ID "
                        f"{courante['invoice_id']}). Le montant et la date ne sont pas "
                        "modifiables ici afin de ne pas désynchroniser la facture. "
                        "Supprimez le règlement depuis la page Factures si nécessaire."
                    )
                donnees, valider = _formulaire(
                    f"modifier_{selection}", courante, "Enregistrer les modifications"
                )
                if valider:
                    try:
                        db.update_transaction(conn, selection, donnees)
                        st.success(f"Transaction n°{selection} mise à jour.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

                theme.section("Suppression définitive")
                st.caption(
                    "La suppression est irréversible. Si l'opération est un règlement de "
                    "facture, le paiement associé est également annulé et le solde de la "
                    "facture est recalculé automatiquement."
                )
                with st.form(key="form_suppression"):
                    confirmation = st.checkbox(
                        f"Je confirme la suppression de la transaction n°{selection}"
                    )
                    supprimer = st.form_submit_button("Supprimer cette transaction")
                if supprimer:
                    if not confirmation:
                        st.error("Cochez la case de confirmation avant de supprimer.")
                    else:
                        try:
                            info = db.delete_transaction(conn, selection)
                            message = f"Transaction n°{selection} supprimée."
                            if info.get("invoice_updated"):
                                message += (
                                    f" Le règlement de la facture "
                                    f"{info['invoice_number']} a été annulé et son solde recalculé."
                                )
                            st.success(message)
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

    # ------------------------------------------------------------- Import
    with onglet_import:
        st.markdown(
            "Colonnes reconnues : `date`, `type`, `categorie`, `description`, `montant`, "
            "`statut`, `date_prevue`, `tiers`, `reference`. Les colonnes `date` et "
            "`montant` sont obligatoires. Séparateur `;` ou `,`, encodage UTF-8 ou Windows."
        )
        theme.download_button(
            "Télécharger le modèle CSV",
            io_utils.csv_template_bytes(),
            "modele_transactions.csv",
            "text/csv",
            "tx_modele",
        )
        fichier = st.file_uploader(
            "Fichier CSV ou Excel (.xlsx)", type=["csv", "xlsx", "xlsm"], key="tx_import"
        )
        if fichier is not None:
            try:
                lignes, erreurs = io_utils.lire_fichier_transactions(fichier, fichier.name)
            except Exception as exc:  # noqa: BLE001
                lignes, erreurs = [], [f"Lecture impossible : {exc}"]
            st.write(f"**{len(lignes)} ligne(s) valide(s)** et **{len(erreurs)} rejetée(s)**.")
            if lignes:
                apercu = pd.DataFrame(
                    [
                        {
                            "Date": ligne["date"],
                            "Type": ligne["type"],
                            "Catégorie": ligne["category"],
                            "Description": ligne["description"],
                            "Montant": ligne["amount"],
                            "Statut": ligne["status"],
                        }
                        for ligne in lignes[:15]
                    ]
                )
                theme.dataframe(theme.style_dataframe(apercu, ["Montant"]), height=260)
            if erreurs:
                with st.expander(f"Détail des {len(erreurs)} ligne(s) rejetée(s)", expanded=True):
                    for erreur in erreurs[:40]:
                        st.write(f"- {erreur}")
            if lignes and st.button("Importer ces transactions", key="tx_import_confirm"):
                try:
                    nombre = db.add_transactions_bulk(conn, lignes)
                    st.success(f"{nombre} transaction(s) importée(s).")
                    st.rerun()
                except ValueError as exc:
                    st.error(f"Import annulé (aucune ligne enregistrée) : {exc}")
