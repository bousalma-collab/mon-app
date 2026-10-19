"""Page « Rapports et paramètres » : reporting periodique, exports, configuration."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

import auth
import db
import demo_data
import finance
import io_utils
import theme


def _periode(ctx: dict) -> tuple[date, date]:
    today = ctx["today"]
    choix = st.selectbox(
        "Période de reporting",
        [
            "Mois en cours",
            "Mois précédent",
            "3 derniers mois",
            "Année en cours",
            "Personnalisée",
        ],
        key="rap_periode",
    )
    if choix == "Mois en cours":
        debut, fin = finance.month_bounds(today)
        return debut, today
    if choix == "Mois précédent":
        precedent = finance.add_months(today.replace(day=1), -1)
        return finance.month_bounds(precedent)
    if choix == "3 derniers mois":
        return finance.add_months(today, -3), today
    if choix == "Année en cours":
        return today.replace(month=1, day=1), today
    colonnes = st.columns(2)
    with colonnes[0]:
        debut = st.date_input("Du", value=today.replace(day=1), key="rap_debut")
    with colonnes[1]:
        fin = st.date_input("Au", value=today, key="rap_fin")
    if fin < debut:
        debut, fin = fin, debut
    return debut, fin


def _synthese(ctx: dict, debut: date, fin: date) -> tuple[dict, list[tuple[str, str]]]:
    settings = ctx["settings"]
    transactions = ctx["transactions"]
    factures = ctx["invoices"]
    today = ctx["today"]
    devise = settings.get("currency") or "MAD"

    ouverture = finance.actual_cash(
        settings, [t for t in transactions if t["date"] and t["date"] < debut]
    )
    cloture = finance.actual_cash(
        settings, [t for t in transactions if t["date"] and t["date"] <= fin]
    )
    totaux = finance.cash_totals(transactions, debut, fin)
    prevision = finance.build_forecast(
        settings, transactions, factures, today, ctx["horizon"], ctx["collection_delay"]
    )
    kpi = finance.forecast_kpis(prevision)
    alertes = finance.build_alerts(settings, transactions, factures, prevision, today)

    retard_clients = finance.overdue_invoices(factures, today, inv_type="Client")
    retard_fournisseurs = finance.overdue_invoices(factures, today, inv_type="Fournisseur")

    donnees = {
        "ouverture": ouverture,
        "cloture": cloture,
        "inflows": totaux["inflows"],
        "outflows": totaux["outflows"],
        "net": totaux["net"],
        "creances": finance.total_receivables(factures),
        "dettes": finance.total_payables(factures),
        "retard_clients": sum(finance.to_decimal(f["remaining"]) for f in retard_clients),
        "nb_retard_clients": len(retard_clients),
        "retard_fournisseurs": sum(
            finance.to_decimal(f["remaining"]) for f in retard_fournisseurs
        ),
        "nb_retard_fournisseurs": len(retard_fournisseurs),
        "prevision_finale": kpi["final_cash"],
        "prevision_min": kpi["min_cash"],
        "prevision_min_date": kpi["min_cash_date"],
        "prevision_nb_jours_sous_seuil": kpi["days_below_threshold"],
        "prevision": prevision,
        "alertes": alertes,
    }
    lignes = [
        ("Entreprise", settings.get("company_name") or "-"),
        ("Période analysée", f"{finance.format_date_fr(debut)} → {finance.format_date_fr(fin)}"),
        ("Devise", devise),
        ("Trésorerie au début de la période (réel)", finance.money_str(ouverture, devise)),
        ("Trésorerie à la fin de la période (réel)", finance.money_str(cloture, devise)),
        ("Encaissements réalisés", finance.money_str(totaux["inflows"], devise)),
        ("Décaissements réalisés", finance.money_str(totaux["outflows"], devise)),
        ("Flux net de trésorerie", finance.money_str(totaux["net"], devise)),
        ("Créances clients restantes", finance.money_str(donnees["creances"], devise)),
        ("Dettes fournisseurs restantes", finance.money_str(donnees["dettes"], devise)),
        (
            "Factures clients en retard",
            f"{donnees['nb_retard_clients']} facture(s) — "
            f"{finance.money_str(donnees['retard_clients'], devise)}",
        ),
        (
            "Factures fournisseurs échues",
            f"{donnees['nb_retard_fournisseurs']} facture(s) — "
            f"{finance.money_str(donnees['retard_fournisseurs'], devise)}",
        ),
        (
            f"Trésorerie prévisionnelle ({ctx['horizon']} jours)",
            f"{finance.money_str(kpi['final_cash'], devise)} "
            f"(minimum {finance.money_str(kpi['min_cash'], devise)} le "
            f"{finance.format_date_fr(kpi['min_cash_date'])})",
        ),
        ("Jours sous le seuil de sécurité", str(kpi["days_below_threshold"])),
        ("Alertes actives", str(len(alertes))),
    ]
    return donnees, lignes


def render(ctx: dict) -> None:
    conn = ctx["conn"]
    settings = ctx["settings"]
    devise = settings.get("currency") or "MAD"
    today = ctx["today"]

    theme.page_title(
        "Rapports et paramètres",
        "Synthèse financière sur une période, exports CSV / Excel / PDF et "
        "configuration de l'application.",
    )
    theme.demo_banner(bool(settings.get("demo_mode")), settings.get("company_name", ""))

    debut, fin = _periode(ctx)
    donnees, lignes = _synthese(ctx, debut, fin)

    theme.kpi_row(
        [
            {
                "label": "Trésorerie au début de la période",
                "value": finance.money_str(donnees["ouverture"], devise),
                "sub": f"Solde réel avant le {finance.format_date_fr(debut)}",
                "tone": "neutral",
            },
            {
                "label": "Trésorerie à la fin de la période",
                "value": finance.money_str(donnees["cloture"], devise),
                "sub": f"Au {finance.format_date_fr(fin)}",
                "tone": "positive" if donnees["cloture"] >= 0 else "danger",
            },
            {
                "label": "Encaissements réalisés",
                "value": finance.money_str(donnees["inflows"], devise),
                "sub": "Mouvements réels entrants",
                "tone": "positive",
            },
            {
                "label": "Décaissements réalisés",
                "value": finance.money_str(donnees["outflows"], devise),
                "sub": "Mouvements réels sortants",
                "tone": "danger",
            },
        ]
    )
    theme.kpi_row(
        [
            {
                "label": "Flux net de trésorerie",
                "value": finance.money_str(donnees["net"], devise),
                "sub": "Réalisé sur la période",
                "tone": "positive" if donnees["net"] >= 0 else "danger",
            },
            {
                "label": "Créances clients restantes",
                "value": finance.money_str(donnees["creances"], devise),
                "sub": f"Dont {finance.money_str(donnees['retard_clients'], devise)} en retard",
                "tone": "danger" if donnees["retard_clients"] > 0 else "info",
            },
            {
                "label": "Dettes fournisseurs restantes",
                "value": finance.money_str(donnees["dettes"], devise),
                "sub": f"Dont {finance.money_str(donnees['retard_fournisseurs'], devise)} échues",
                "tone": "warning" if donnees["dettes"] > 0 else "neutral",
            },
            {
                "label": f"Trésorerie prévisionnelle ({ctx['horizon']} j)",
                "value": finance.money_str(donnees["prevision_finale"], devise),
                "sub": f"Minimum {finance.money_str(donnees['prevision_min'], devise)} le "
                f"{finance.format_date_fr(donnees['prevision_min_date'])}",
                "tone": "positive" if donnees["prevision_min"] >= 0 else "danger",
            },
        ]
    )

    theme.section("Synthèse du rapport")
    tableau = pd.DataFrame(lignes, columns=["Indicateur", "Valeur"])
    theme.dataframe(tableau, height=420, hide_index=True)
    st.caption(
        "Les montants « réalisés » proviennent des opérations au statut Réalisé. "
        "Les montants prévisionnels sont des estimations distinctes, clairement identifiées."
    )

    theme.section("Alertes de la période")
    theme.render_alerts(donnees["alertes"], colonnes=2)

    # ------------------------------------------------------------- Exports
    theme.section("Exports")
    transactions_periode = [
        t for t in ctx["transactions"] if t["date"] and debut <= t["date"] <= fin
    ]
    df_transactions = io_utils.transactions_dataframe(transactions_periode)
    df_factures = io_utils.invoices_dataframe(ctx["invoices"], today)
    df_paiements = io_utils.payments_dataframe(db.list_payments(conn))
    df_prevision = io_utils.forecast_dataframe(donnees["prevision"])
    df_synthese = pd.DataFrame(lignes, columns=["Indicateur", "Valeur"])
    df_alertes = pd.DataFrame(
        [{"Niveau": a["level"], "Alerte": a["title"], "Détail": a["message"]} for a in donnees["alertes"]]
    )

    colonnes = st.columns(4)
    with colonnes[0]:
        theme.download_button(
            "Synthèse (CSV)",
            io_utils.to_csv_bytes(df_synthese),
            f"rapport_synthese_{fin.isoformat()}.csv",
            "text/csv",
            "rap_csv",
        )
    with colonnes[1]:
        theme.download_button(
            "Rapport complet (Excel)",
            io_utils.to_excel_bytes(
                {
                    "Synthèse": df_synthese,
                    "Transactions": df_transactions,
                    "Factures": df_factures,
                    "Paiements": df_paiements,
                    "Prévision": df_prevision,
                    "Alertes": df_alertes,
                }
            ),
            f"rapport_cashflow_{debut.isoformat()}_{fin.isoformat()}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "rap_xlsx",
        )
    with colonnes[2]:
        if io_utils.HAS_REPORTLAB:
            pdf = io_utils.pdf_report_bytes(
                settings.get("company_name") or "CashFlow AI",
                {
                    "Synthèse": lignes,
                    "Alertes": "\n".join(
                        f"[{a['level'].upper()}] {a['title']} : {a['message']}"
                        for a in donnees["alertes"]
                    ),
                    "Transactions de la période": df_transactions.head(40),
                    "Factures": df_factures.head(40),
                    "Prévision quotidienne": df_prevision.head(40),
                },
            )
            if pdf:
                theme.download_button(
                    "Rapport (PDF)",
                    pdf,
                    f"rapport_cashflow_{fin.isoformat()}.pdf",
                    "application/pdf",
                    "rap_pdf",
                )
        else:
            st.info("PDF indisponible : la bibliothèque reportlab n'est pas installée.")
    with colonnes[3]:
        theme.download_button(
            "Transactions (CSV)",
            io_utils.to_csv_bytes(df_transactions),
            f"transactions_{debut.isoformat()}_{fin.isoformat()}.csv",
            "text/csv",
            "rap_tx_csv",
        )

    # -------------------------------------------------------- Paramètres
    theme.section("Paramètres de l'entreprise")
    with st.form("form_parametres"):
        colonnes = st.columns(2)
        with colonnes[0]:
            nom = st.text_input(
                "Nom de l'entreprise", value=settings.get("company_name") or ""
            )
            devise_saisie = st.text_input(
                "Devise (version 1 : MAD)", value=settings.get("currency") or "MAD",
                disabled=True,
            )
            solde_ouverture = st.number_input(
                "Solde d'ouverture (MAD)",
                value=float(settings.get("opening_cash") or 0),
                step=1000.0,
                format="%.2f",
                help="Trésorerie disponible avant la première transaction enregistrée.",
            )
        with colonnes[1]:
            date_ouverture = st.date_input(
                "Date du solde d'ouverture",
                value=settings.get("opening_cash_date") or today,
                key="param_date_ouverture",
            )
            seuil = st.number_input(
                "Seuil minimum de trésorerie (MAD)",
                min_value=0.0,
                value=float(settings.get("min_cash_threshold") or 0),
                step=1000.0,
                format="%.2f",
                help="Sous ce seuil, l'application déclenche une alerte.",
            )
            mode_demo = st.checkbox(
                "Mode démonstration (données fictives)",
                value=bool(settings.get("demo_mode")),
            )
        enregistrer = st.form_submit_button("Enregistrer les paramètres")
    if enregistrer:
        try:
            db.update_settings(
                conn,
                company_name=nom,
                currency=devise_saisie or "MAD",
                opening_cash=solde_ouverture,
                opening_cash_date=date_ouverture,
                min_cash_threshold=seuil,
                demo_mode=1 if mode_demo else 0,
            )
            st.success("Paramètres enregistrés.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    stats = db.database_stats(conn)
    st.caption(
        f"Base de données locale : {stats['path']} — {stats['transactions']} transaction(s), "
        f"{stats['invoices']} facture(s), {stats['payments']} paiement(s)."
    )

    # ------------------------------------------------- Mon compte
    theme.section("Mon compte")
    utilisateur = st.session_state.get("utilisateur") or {}
    col_infos, col_code = st.columns([1, 1.6])
    with col_infos:
        st.markdown(
            f"**{utilisateur.get('full_name') or utilisateur.get('username')}**  \n"
            f"Identifiant : `{utilisateur.get('username', '')}`  \n"
            f"Rôle : {auth.libelle_role(utilisateur.get('role', 'lecteur'))}"
        )
    with col_code:
        with st.form("form_mon_code"):
            ancien = st.text_input(
                "Code actuel", type="password", key="mon_code_ancien"
            )
            nouveau = st.text_input(
                "Nouveau code", type="password", key="mon_code_nouveau"
            )
            confirme = st.text_input(
                "Confirmer le nouveau code", type="password", key="mon_code_confirme"
            )
            changer_code = st.form_submit_button("Changer mon code")
        if changer_code:
            try:
                if not db.authenticate(
                    conn, utilisateur.get("username", ""), ancien
                ):
                    raise ValueError("Le code actuel est incorrect.")
                if nouveau != confirme:
                    raise ValueError(
                        "Les deux saisies du nouveau code ne correspondent pas."
                    )
                db.update_user_code(conn, int(utilisateur["id"]), nouveau)
                st.success("Votre code d'accès a été modifié.")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    # ------------------------------------------------- Utilisateurs
    if utilisateur.get("role") == "admin":
        theme.section("Utilisateurs")
        st.caption(
            "Comptes autorisés à ouvrir l'application. Les codes ne sont jamais "
            "affichés : ils peuvent seulement être réinitialisés."
        )
        comptes = db.list_users(conn)
        lignes = [
            {
                "Identifiant": compte["username"],
                "Nom": compte["full_name"] or "—",
                "Rôle": auth.libelle_role(compte["role"]),
                "Statut": "Actif" if compte["is_active"] else "Désactivé",
                "Dernière connexion": (
                    finance.format_date_fr(compte["last_login_at"])
                    if compte["last_login_at"]
                    else "—"
                ),
            }
            for compte in comptes
        ]
        theme.dataframe(pd.DataFrame(lignes), hide_index=True)

        with st.expander("Ajouter un utilisateur"):
            with st.form("form_ajout_utilisateur"):
                nouveau_nom = st.text_input(
                    "Nom d'utilisateur", key="new_user_nom", placeholder="ex. salma"
                )
                nouveau_libelle = st.text_input(
                    "Nom affiché", key="new_user_libelle", placeholder="ex. Salma B."
                )
                nouveau_role = st.selectbox(
                    "Rôle",
                    ["lecteur", "admin"],
                    format_func=auth.libelle_role,
                    key="new_user_role",
                )
                nouveau_code = st.text_input(
                    "Code d'accès", type="password", key="new_user_code"
                )
                nouveau_code_bis = st.text_input(
                    "Confirmer le code", type="password", key="new_user_code_bis"
                )
                creer = st.form_submit_button("Créer le compte")
            if creer:
                try:
                    if nouveau_code != nouveau_code_bis:
                        raise ValueError("Les deux saisies du code ne correspondent pas.")
                    db.create_user(
                        conn,
                        nouveau_nom,
                        nouveau_code,
                        nouveau_libelle,
                        nouveau_role,
                    )
                    st.success(f"Compte « {nouveau_nom.strip().lower()} » créé.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

        with st.expander("Gérer un compte"):
            noms = [compte["username"] for compte in comptes]
            selection = st.selectbox("Compte à gérer", noms, key="admin_compte")
            cible = next(c for c in comptes if c["username"] == selection)
            st.caption(
                f"{cible['full_name'] or '—'} · {auth.libelle_role(cible['role'])} · "
                + ("actif" if cible["is_active"] else "désactivé")
            )
            code_reinit = st.text_input(
                "Nouveau code", type="password", key=f"reinit_code_{selection}"
            )
            col_reset, col_etat, col_suppr = st.columns(3)
            if col_reset.button("Réinitialiser le code", key=f"btn_reinit_{selection}"):
                try:
                    db.update_user_code(conn, int(cible["id"]), code_reinit)
                    st.success(f"Code de « {selection} » réinitialisé.")
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
            libelle_etat = "Désactiver" if cible["is_active"] else "Réactiver"
            if col_etat.button(libelle_etat, key=f"btn_etat_{selection}"):
                try:
                    db.set_user_active(conn, int(cible["id"]), not cible["is_active"])
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
            if col_suppr.button("Supprimer", key=f"btn_suppr_{selection}"):
                try:
                    if int(cible["id"]) == int(utilisateur.get("id", 0)):
                        raise ValueError(
                            "Vous ne pouvez pas supprimer le compte avec lequel "
                            "vous êtes connecté."
                        )
                    db.delete_user(conn, int(cible["id"]))
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

    # ------------------------------------------------- Données de démo
    theme.section("Données de démonstration")
    st.markdown(
        "Le jeu de démonstration décrit une PME marocaine **fictive** "
        "(*Atlas Distribution SARL*, MAD) : historique de 4 mois, factures clients et "
        "fournisseurs, paiements partiels, une facture client en retard, des "
        "encaissements attendus, des décaissements prévus et un risque de tension de "
        "trésorerie à 3 semaines."
    )
    with st.form("form_demo"):
        confirmation_demo = st.checkbox(
            "Je comprends que le chargement remplace toutes les données actuelles "
            "(transactions, factures, paiements)"
        )
        charger = st.form_submit_button("Charger / réinitialiser les données de démonstration")
    if charger:
        if not confirmation_demo:
            st.error("Cochez la case de confirmation pour éviter d'écraser vos données par erreur.")
        else:
            try:
                resume = demo_data.load_demo_data(conn, today)
                st.success(
                    "Données de démonstration chargées : "
                    f"{resume['completed_transactions']} opération(s) réalisée(s), "
                    f"{resume['planned_transactions']} opération(s) prévue(s), "
                    f"{resume['client_invoices']} facture(s) client, "
                    f"{resume['supplier_invoices']} facture(s) fournisseur, "
                    f"{resume['payments']} paiement(s)."
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Chargement impossible : {exc}")

    theme.section("Effacer les données")
    with st.form("form_effacement"):
        confirmation = st.checkbox(
            "Je confirme l'effacement de toutes les transactions, factures et paiements"
        )
        effacer = st.form_submit_button("Effacer toutes les données")
    if effacer:
        if not confirmation:
            st.error("Cochez la case de confirmation avant d'effacer.")
        else:
            db.clear_all_data(conn)
            db.update_settings(conn, demo_mode=0)
            st.success("Toutes les données ont été effacées. Les paramètres sont conservés.")
            st.rerun()
