"""Page « Tableau de bord » : indicateurs, alertes et graphiques."""

from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go
import streamlit as st

import finance
import io_utils
import theme


def render(ctx: dict) -> None:
    settings = ctx["settings"]
    transactions = ctx["transactions"]
    factures = ctx["invoices"]
    today = ctx["today"]
    devise = settings.get("currency") or "MAD"
    seuil = settings.get("min_cash_threshold") or 0

    prevision = finance.build_forecast(
        settings, transactions, factures, today, ctx["horizon"], ctx["collection_delay"]
    )

    theme.page_title(
        "Tableau de bord",
        "Vue consolidée de la trésorerie réelle et prévisionnelle de l'entreprise.",
    )
    theme.demo_banner(bool(settings.get("demo_mode")), settings.get("company_name", ""))

    # ------------------------------------------------------------------ KPI
    mois_debut, mois_fin = finance.month_bounds(today)
    totaux_mois = finance.cash_totals(transactions, mois_debut, mois_fin)
    tresorerie = finance.actual_cash(settings, transactions)
    creances = finance.total_receivables(factures)
    dettes = finance.total_payables(factures)
    kpi = finance.forecast_kpis(prevision)

    tone_tresorerie = "positive"
    if tresorerie < 0:
        tone_tresorerie = "danger"
    elif seuil and tresorerie < seuil:
        tone_tresorerie = "warning"

    tone_prevision = "positive"
    if kpi["first_negative_date"]:
        tone_prevision = "danger"
    elif seuil and kpi["min_cash"] < seuil:
        tone_prevision = "warning"

    en_retard_clients = finance.overdue_invoices(factures, today, inv_type="Client")
    retard_total = sum(finance.to_decimal(f["remaining"]) for f in en_retard_clients)

    theme.kpi_row(
        [
            {
                "label": "Trésorerie actuelle",
                "value": finance.money_str(tresorerie, devise),
                "sub": (
                    "Solde de départ du compte "
                    f"{finance.money_str(settings.get('opening_cash'), devise)}"
                ),
                "tone": tone_tresorerie,
            },
            {
                "label": "Encaissements réalisés du mois",
                "value": finance.money_str(totaux_mois["inflows"], devise),
                "sub": f"Du {finance.format_date_fr(mois_debut)} au {finance.format_date_fr(mois_fin)}",
                "tone": "positive",
            },
            {
                "label": "Décaissements réalisés du mois",
                "value": finance.money_str(totaux_mois["outflows"], devise),
                "sub": f"Du {finance.format_date_fr(mois_debut)} au {finance.format_date_fr(mois_fin)}",
                "tone": "danger" if totaux_mois["outflows"] > totaux_mois["inflows"] else "neutral",
            },
            {
                "label": "Flux net du mois",
                "value": finance.money_str(totaux_mois["net"], devise),
                "sub": "Encaissements - décaissements réalisés",
                "tone": "positive" if totaux_mois["net"] >= 0 else "danger",
            },
        ]
    )
    theme.kpi_row(
        [
            {
                "label": "Créances clients restantes",
                "value": finance.money_str(creances, devise),
                "sub": (
                    f"Dont {finance.money_str(retard_total, devise)} en retard "
                    f"({len(en_retard_clients)} facture(s))"
                    if en_retard_clients
                    else "Aucune facture client en retard"
                ),
                "tone": "danger" if en_retard_clients else "info",
            },
            {
                "label": "Dettes fournisseurs restantes",
                "value": finance.money_str(dettes, devise),
                "sub": "Factures fournisseurs non soldées",
                "tone": "warning" if dettes > 0 else "neutral",
            },
            {
                "label": f"Trésorerie prévisionnelle à {ctx['horizon']} jours",
                "value": finance.money_str(kpi["final_cash"], devise),
                "sub": (
                    f"Minimum {finance.money_str(kpi['min_cash'], devise)} le "
                    f"{finance.format_date_fr(kpi['min_cash_date'])}"
                ),
                "tone": tone_prevision,
            },
        ],
        colonnes_par_ligne=3,
    )

    # --------------------------------------------------------------- Alertes
    theme.section("Alertes et points de vigilance")
    alertes = finance.build_alerts(settings, transactions, factures, prevision, today)
    theme.render_alerts(alertes, colonnes=2)

    # ------------------------------------------------------------- Graphiques
    theme.section("Graphiques de trésorerie")

    colonne_gauche, colonne_droite = st.columns(2)

    with colonne_gauche:
        st.markdown("**Évolution de la trésorerie réelle (90 jours)**")
        debut = today - timedelta(days=90)
        serie = finance.cash_balance_series(settings, transactions, debut, today)
        figure = theme.line_chart(
            [p["date"] for p in serie],
            [p["balance"] for p in serie],
            "Trésorerie réelle",
            theme.BLUE,
            seuil=seuil or None,
            remplissage="rgba(37,99,168,0.10)",
        )
        figure.add_hline(y=0, line_color=theme.RED, line_width=1, line_dash="dash")
        figure.update_yaxes(title_text="MAD")
        theme.plot(figure, height=330)

    with colonne_droite:
        st.markdown("**Encaissements et décaissements réalisés par mois**")
        serie_mois = finance.monthly_cash_series(transactions, today, 6)
        figure = go.Figure()
        figure.add_trace(
            go.Bar(
                x=[m["label"] for m in serie_mois],
                y=[m["inflows"] for m in serie_mois],
                name="Encaissements",
                marker_color=theme.GREEN,
                hovertemplate="%{x}<br>%{y:,.2f} MAD<extra></extra>",
            )
        )
        figure.add_trace(
            go.Bar(
                x=[m["label"] for m in serie_mois],
                y=[m["outflows"] for m in serie_mois],
                name="Décaissements",
                marker_color=theme.RED,
                hovertemplate="%{x}<br>%{y:,.2f} MAD<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[m["label"] for m in serie_mois],
                y=[m["net"] for m in serie_mois],
                name="Flux net",
                mode="lines+markers",
                line=dict(color=theme.NAVY, width=2),
                hovertemplate="%{x}<br>%{y:,.2f} MAD<extra></extra>",
            )
        )
        figure.update_layout(barmode="group")
        figure.update_yaxes(title_text="MAD")
        theme.plot(figure, height=330)

    st.markdown(
        f"**Trésorerie projetée sur {ctx['horizon']} jours** "
        f"<span style='color:{theme.GREY};font-size:.85rem'>"
        "— estimation à partir des opérations prévues et des factures non réglées</span>",
        unsafe_allow_html=True,
    )
    figure = go.Figure()
    jours = prevision["days"]
    figure.add_trace(
        go.Scatter(
            x=[j["date"] for j in jours],
            y=[j["closing"] for j in jours],
            name="Trésorerie projetée",
            mode="lines",
            line=dict(color=theme.BLUE, width=2.6),
            fill="tozeroy",
            fillcolor="rgba(37,99,168,0.10)",
            hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.2f} MAD<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[j["date"] for j in jours],
            y=[j["outflows"] for j in jours],
            name="Décaissements du jour",
            mode="lines",
            line=dict(color=theme.RED, width=1, dash="dot"),
            hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.2f} MAD<extra></extra>",
        )
    )
    if seuil:
        figure.add_hline(
            y=seuil,
            line_dash="dot",
            line_color=theme.AMBER,
            annotation_text=f"Seuil {seuil:,.0f} MAD".replace(",", " "),
            annotation_position="top left",
        )
    figure.add_hline(y=0, line_color=theme.RED, line_width=1)
    figure.update_yaxes(title_text="MAD")
    theme.plot(figure, height=340)
    theme.note(
        "Prévision = estimation. Elle ne compte que les opérations <strong>réalisées</strong> "
        "dans la trésorerie réelle, puis ajoute les opérations prévues et les factures non "
        f"réglées (délai de recouvrement estimé : {ctx['collection_delay']} jours pour les "
        "impayés clients)."
    )

    # ------------------------------------------------------------- Tableaux
    theme.section("Dernières opérations et factures sensibles")
    colonne_gauche, colonne_droite = st.columns(2)

    with colonne_gauche:
        st.markdown("**10 dernières transactions**")
        recentes = sorted(
            transactions, key=lambda t: (t["date"], t["id"]), reverse=True
        )[:10]
        if recentes:
            df = io_utils.transactions_dataframe(recentes)[
                ["Date", "Type", "Catégorie", "Description", "Montant (MAD)", "Statut"]
            ]
            theme.dataframe(theme.style_dataframe(df, ["Montant (MAD)"]), height=380)
        else:
            st.info("Aucune transaction enregistrée pour le moment.")

    with colonne_droite:
        st.markdown("**Factures clients en retard**")
        if en_retard_clients:
            df = io_utils.invoices_dataframe(en_retard_clients, today)[
                ["N° facture", "Tiers", "Échéance", "Restant (MAD)", "Retard (jours)"]
            ]
            theme.dataframe(theme.style_dataframe(df, ["Restant (MAD)"]), height=380)
        else:
            st.success("Aucune facture client en retard.")
