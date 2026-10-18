"""Page « Factures » : factures clients et fournisseurs, règlements de paiement."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

import db
import finance
import io_utils
import theme


def render(ctx: dict) -> None:
    conn = ctx["conn"]
    settings = ctx["settings"]
    devise = settings.get("currency") or "MAD"
    today = ctx["today"]
    factures = db.list_invoices(conn)

    theme.page_title(
        "Factures",
        "Suivi des créances clients et des dettes fournisseurs, avec règlements "
        "partiels et rapprochement automatique avec la trésorerie.",
    )
    theme.demo_banner(bool(settings.get("demo_mode")), settings.get("company_name", ""))

    creances = finance.total_receivables(factures)
    dettes = finance.total_payables(factures)
    retard_clients = finance.overdue_invoices(factures, today, inv_type="Client")
    retard_fournisseurs = finance.overdue_invoices(factures, today, inv_type="Fournisseur")
    total_retard = sum(finance.to_decimal(f["remaining"]) for f in retard_clients)

    theme.kpi_row(
        [
            {
                "label": "Créances clients restantes",
                "value": finance.money_str(creances, devise),
                "sub": f"{len([f for f in factures if f['type'] == 'Client' and f['remaining'] > 0])} facture(s) non soldée(s)",
                "tone": "info",
            },
            {
                "label": "Dettes fournisseurs restantes",
                "value": finance.money_str(dettes, devise),
                "sub": f"{len([f for f in factures if f['type'] == 'Fournisseur' and f['remaining'] > 0])} facture(s) à payer",
                "tone": "warning",
            },
            {
                "label": "Factures clients en retard",
                "value": finance.money_str(total_retard, devise),
                "sub": f"{len(retard_clients)} facture(s) échue(s)",
                "tone": "danger" if retard_clients else "positive",
            },
            {
                "label": "Factures fournisseurs échues",
                "value": finance.money_str(
                    sum(finance.to_decimal(f["remaining"]) for f in retard_fournisseurs), devise
                ),
                "sub": f"{len(retard_fournisseurs)} facture(s) à régler sans délai",
                "tone": "danger" if retard_fournisseurs else "positive",
            },
        ]
    )

    # ------------------------------------------------------------- Filtres
    colonnes = st.columns([1.3, 1.6, 2, 1.4])
    with colonnes[0]:
        filtre_type = st.selectbox("Type de facture", ["Toutes", "Client", "Fournisseur"], key="inv_type")
    with colonnes[1]:
        filtre_statut = st.selectbox(
            "Statut", ["Tous", "Ouverte", "Partiellement payée", "En retard", "Payée"], key="inv_statut"
        )
    with colonnes[2]:
        recherche = st.text_input("Recherche (numéro ou tiers)", key="inv_recherche")
    with colonnes[3]:
        non_soldees = st.checkbox("Seulement les non soldées", value=False, key="inv_non_soldees")

    filtrees = db.list_invoices(
        conn,
        inv_type=None if filtre_type == "Toutes" else filtre_type,
        status=None if filtre_statut == "Tous" else filtre_statut,
        search=recherche.strip() or None,
        only_unpaid=non_soldees,
    )

    theme.section(f"{len(filtrees)} facture(s) affichée(s)")
    if filtrees:
        df = io_utils.invoices_dataframe(filtrees, today)
        theme.dataframe(theme.style_dataframe(df, ["Total (MAD)", "Payé (MAD)", "Restant (MAD)"]), height=400)
        colonnes_export = st.columns([1, 1, 3])
        with colonnes_export[0]:
            theme.download_button(
                "Exporter en CSV", io_utils.to_csv_bytes(df),
                f"factures_{today.isoformat()}.csv", "text/csv", "inv_export_csv",
            )
        with colonnes_export[1]:
            theme.download_button(
                "Exporter en Excel", io_utils.to_excel_bytes({"Factures": df}),
                f"factures_{today.isoformat()}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "inv_export_xlsx",
            )
    else:
        st.info("Aucune facture ne correspond aux filtres sélectionnés.")

    onglet_creation, onglet_edition, onglet_paiement, onglet_historique = st.tabs(
        ["Nouvelle facture", "Modifier ou supprimer", "Enregistrer un paiement", "Historique des paiements"]
    )

    # ----------------------------------------------------------- Création
    with onglet_creation:
        numero_defaut = db.next_invoice_number(conn, "Client", today.year)
        with st.form("form_facture_creation"):
            colonnes = st.columns(2)
            with colonnes[0]:
                type_facture = st.selectbox("Type *", list(finance.INVOICE_TYPES), key="new_inv_type")
                numero = st.text_input("Numéro de facture *", value=numero_defaut, key="new_inv_num")
                tiers = st.text_input("Client ou fournisseur *", key="new_inv_tiers")
                emission = st.date_input("Date d'émission *", value=today, key="new_inv_emission")
                echeance = st.date_input(
                    "Date d'échéance *", value=today + timedelta(days=30), key="new_inv_echeance"
                )
            with colonnes[1]:
                total = st.number_input(
                    "Montant total (MAD) *", min_value=0.0, value=0.0, step=500.0,
                    format="%.2f", key="new_inv_total",
                )
                notes = st.text_area("Notes", key="new_inv_notes", height=110)
                st.caption(
                    "Une facture n'est pas un mouvement de trésorerie : seul son règlement "
                    "crée une opération réelle. Le montant payé reste donc à 0 à la création, "
                    "puis évolue via l'onglet « Enregistrer un paiement »."
                )
            creer = st.form_submit_button("Créer la facture")
        if creer:
            try:
                identifiant = db.add_invoice(
                    conn,
                    {
                        "number": numero,
                        "type": type_facture,
                        "party": tiers,
                        "issue_date": emission,
                        "due_date": echeance,
                        "total": total,
                        "paid": 0,
                        "notes": notes,
                    },
                )
                st.success(f"Facture {numero} créée (ID {identifiant}).")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    # ------------------------------------------------------------ Édition
    with onglet_edition:
        if not factures:
            st.info("Aucune facture à modifier.")
        else:
            options = [f["id"] for f in factures]

            def _etiquette(identifiant: int) -> str:
                f = next((x for x in factures if x["id"] == identifiant), None)
                if f is None:
                    return str(identifiant)
                return (
                    f"{f['number']} — {f['type']} — {f['party']} — "
                    f"{finance.money_str(f['total'], devise)} — "
                    f"restant {finance.money_str(f['remaining'], devise)}"
                )

            selection = st.selectbox(
                "Facture à modifier", options, format_func=_etiquette, key="inv_edition_id"
            )
            courante = next((f for f in factures if f["id"] == selection), None)
            if courante is not None:
                with st.form(key=f"form_facture_edition_{selection}"):
                    colonnes = st.columns(2)
                    with colonnes[0]:
                        numero = st.text_input("Numéro *", value=courante["number"])
                        type_facture = st.selectbox(
                            "Type *",
                            list(finance.INVOICE_TYPES),
                            index=list(finance.INVOICE_TYPES).index(courante["type"]),
                        )
                        tiers = st.text_input("Client ou fournisseur *", value=courante["party"])
                    with colonnes[1]:
                        emission = st.date_input(
                            "Date d'émission *",
                            value=courante["issue_date"] or today,
                            key="edit_inv_emission",
                        )
                        echeance = st.date_input(
                            "Date d'échéance",
                            value=courante["due_date"] or today,
                            key="edit_inv_echeance",
                        )
                        total = st.number_input(
                            "Montant total (MAD) *", min_value=0.0,
                            value=float(courante["total"]), step=500.0, format="%.2f",
                        )
                        paye = st.number_input(
                            "Montant payé (MAD)", min_value=0.0,
                            value=float(courante["paid"]), step=500.0, format="%.2f",
                            help="Modifiable uniquement si aucun règlement n'est enregistré.",
                        )
                        notes = st.text_area("Notes", value=courante.get("notes", ""), height=80)
                    enregistrer = st.form_submit_button("Enregistrer les modifications")
                if enregistrer:
                    try:
                        if courante["paid"] > 0 and abs(paye - courante["paid"]) > 0.005:
                            raise ValueError(
                                "Des règlements existent déjà pour cette facture : le montant "
                                "payé ne peut pas être modifié manuellement. Enregistrez ou "
                                "annulez un règlement depuis l'onglet « Enregistrer un paiement »."
                            )
                        db.update_invoice(
                            conn,
                            selection,
                            {
                                "number": numero,
                                "type": type_facture,
                                "party": tiers,
                                "issue_date": emission,
                                "due_date": echeance,
                                "total": total,
                                "paid": paye,
                                "notes": notes,
                            },
                        )
                        st.success(f"Facture {numero} mise à jour.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

                theme.section("Suppression")
                st.caption(
                    "La suppression d'une facture supprime aussi ses règlements et les "
                    "opérations de trésorerie associées."
                )
                with st.form(key=f"form_facture_suppression_{selection}"):
                    confirmation = st.checkbox(
                        f"Je confirme la suppression de la facture {courante['number']} "
                        f"et de ses règlements"
                    )
                    supprimer = st.form_submit_button("Supprimer cette facture")
                if supprimer:
                    if not confirmation:
                        st.error("Cochez la case de confirmation avant de supprimer.")
                    else:
                        try:
                            info = db.delete_invoice(conn, selection)
                            st.success(
                                f"Facture {info['invoice']} supprimée "
                                f"({info['linked_transactions']} opération(s) de trésorerie associée(s))."
                            )
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

    # ------------------------------------------------------------ Paiement
    with onglet_paiement:
        non_soldees = [f for f in factures if finance.to_decimal(f["remaining"]) > 0]
        if not non_soldees:
            st.info("Toutes les factures sont soldées.")
        else:
            options = [f["id"] for f in non_soldees]

            def _etiquette_paiement(identifiant: int) -> str:
                f = next((x for x in non_soldees if x["id"] == identifiant), None)
                if f is None:
                    return str(identifiant)
                return (
                    f"{f['number']} — {f['type']} — {f['party']} — restant "
                    f"{finance.money_str(f['remaining'], devise)} — échéance "
                    f"{finance.format_date_fr(f['due_date'])}"
                )

            identifiant = st.selectbox(
                "Facture à régler", options, format_func=_etiquette_paiement, key="pay_invoice"
            )
            facture = next((f for f in non_soldees if f["id"] == identifiant), None)
            if facture is not None:
                restant = finance.invoice_remaining(facture)
                st.markdown(
                    theme.kpi_card(
                        f"Solde restant — {facture['number']}",
                        finance.money_str(restant, devise),
                        f"Total {finance.money_str(facture['total'], devise)} — "
                        f"déjà payé {finance.money_str(facture['paid'], devise)} — "
                        f"statut {finance.compute_invoice_status(facture, today)}",
                        "warning" if facture["due_date"] and facture["due_date"] < today else "info",
                    ),
                    unsafe_allow_html=True,
                )
                with st.form(key=f"form_paiement_{identifiant}"):
                    colonnes = st.columns(3)
                    with colonnes[0]:
                        montant = st.number_input(
                            "Montant du paiement (MAD) *",
                            min_value=0.0,
                            max_value=float(restant),
                            value=float(restant),
                            step=500.0,
                            format="%.2f",
                        )
                    with colonnes[1]:
                        date_paiement = st.date_input(
                            "Date du paiement *", value=today, max_value=today
                        )
                    with colonnes[2]:
                        note = st.text_input("Commentaire", placeholder="Virement, chèque, espèces…")
                    st.caption(
                        "Le paiement crée une transaction réalisée liée à la facture "
                        "(encaissement pour un client, décaissement pour un fournisseur). "
                        "Un seul paiement identique par jour est accepté."
                    )
                    valider = st.form_submit_button("Enregistrer le paiement")
                if valider:
                    try:
                        resultat = db.record_payment(
                            conn, identifiant, montant, date_paiement, note
                        )
                        st.success(
                            f"Paiement de {finance.money_str(resultat['amount'], devise)} "
                            f"enregistré pour la facture {resultat['invoice_number']} "
                            f"(transaction n°{resultat['transaction_id']}). Nouveau solde : "
                            f"{finance.money_str(resultat['remaining'], devise)} — statut "
                            f"{resultat['new_status']}."
                        )
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

    # --------------------------------------------------------- Historique
    with onglet_historique:
        paiements = db.list_payments(conn)
        if paiements:
            df = io_utils.payments_dataframe(paiements)
            theme.dataframe(theme.style_dataframe(df, ["Montant (MAD)"]), height=380)
            theme.download_button(
                "Exporter les paiements (CSV)",
                io_utils.to_csv_bytes(df),
                f"paiements_{today.isoformat()}.csv",
                "text/csv",
                "pay_export_csv",
            )
        else:
            st.info("Aucun paiement enregistré pour le moment.")
