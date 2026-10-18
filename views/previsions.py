"""Page « Prévisions » : projection deterministe de tresorerie sur 7 a 90 jours."""

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

    theme.page_title(
        "Prévisions de trésorerie",
        "Projection jour par jour à partir des opérations prévues et des factures non "
        "réglées. Méthode déterministe : aucune donnée inventée, aucun modèle opaque.",
    )
    theme.demo_banner(bool(settings.get("demo_mode")), settings.get("company_name", ""))

    colonnes = st.columns([1.4, 2.4, 1.6])
    with colonnes[0]:
        horizon = int(ctx["horizon"])
        st.markdown(
            theme.kpi_card(
                "Horizon de prévision",
                f"{horizon} jours",
                "Modifiable dans la barre latérale (7, 30, 60 ou 90 jours)",
                "info",
            ),
            unsafe_allow_html=True,
        )
    with colonnes[1]:
        delai = st.slider(
            "Délai estimé de recouvrement des impayés clients (jours)",
            min_value=0,
            max_value=45,
            value=int(ctx["collection_delay"]),
            key="collection_delay",
            help=(
                "Une facture client déjà échue est supposée être encaissée dans ce délai. "
                "Les dettes fournisseurs échues sont, par prudence, considérées comme "
                "payables immédiatement."
            ),
        )
    with colonnes[2]:
        seuil = settings.get("min_cash_threshold") or 0
        st.markdown(
            theme.kpi_card(
                "Seuil de sécurité",
                finance.money_str(seuil, devise),
                "Modifiable dans « Rapports et paramètres »",
                "warning" if seuil else "neutral",
            ),
            unsafe_allow_html=True,
        )

    prevision = finance.build_forecast(
        settings, transactions, factures, today, horizon, delai
    )
    kpi = finance.forecast_kpis(prevision)
    risque = finance.liquidity_risk_score(settings, transactions, factures, prevision)

    theme.kpi_row(
        [
            {
                "label": "Trésorerie de départ (réelle)",
                "value": finance.money_str(prevision["opening_cash"], devise),
                "sub": f"Constatée le {finance.format_date_fr(today)}",
                "tone": "neutral",
            },
            {
                "label": "Trésorerie projetée en fin d'horizon",
                "value": finance.money_str(kpi["final_cash"], devise),
                "sub": f"Le {finance.format_date_fr(prevision['end_date'])}",
                "tone": "positive" if kpi["final_cash"] >= 0 else "danger",
            },
            {
                "label": "Minimum projeté",
                "value": finance.money_str(kpi["min_cash"], devise),
                "sub": f"Le {finance.format_date_fr(kpi['min_cash_date'])}",
                "tone": (
                    "danger"
                    if kpi["min_cash"] < 0
                    else ("warning" if seuil and kpi["min_cash"] < seuil else "positive")
                ),
            },
            {
                "label": "Première trésorerie négative",
                "value": (
                    finance.format_date_fr(kpi["first_negative_date"])
                    if kpi["first_negative_date"]
                    else "Aucune"
                ),
                "sub": (
                    f"{kpi['days_below_threshold']} jour(s) sous le seuil de "
                    f"{finance.money_str(seuil, devise)}"
                ),
                "tone": "danger" if kpi["first_negative_date"] else "positive",
            },
        ]
    )
    theme.kpi_row(
        [
            {
                "label": "Encaissements attendus",
                "value": finance.money_str(kpi["total_inflows"], devise),
                "sub": "Opérations prévues + factures clients non réglées",
                "tone": "positive",
            },
            {
                "label": "Décaissements attendus",
                "value": finance.money_str(kpi["total_outflows"], devise),
                "sub": "Opérations prévues + factures fournisseurs non réglées",
                "tone": "danger",
            },
            {
                "label": "Flux net attendu",
                "value": finance.money_str(kpi["net_flow"], devise),
                "sub": "Sur la totalité de l'horizon",
                "tone": "positive" if kpi["net_flow"] >= 0 else "danger",
            },
            {
                "label": "Score de risque de liquidité",
                "value": f"{risque['score']}/100",
                "sub": risque["label"],
                "tone": risque["level"],
            },
        ]
    )

    theme.section("Projection de trésorerie")
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
        go.Bar(
            x=[j["date"] for j in jours],
            y=[j["inflows"] for j in jours],
            name="Encaissements du jour",
            marker_color="rgba(18,135,111,0.55)",
            hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.2f} MAD<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            x=[j["date"] for j in jours],
            y=[-j["outflows"] for j in jours],
            name="Décaissements du jour",
            marker_color="rgba(192,57,43,0.55)",
            hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.2f} MAD<extra></extra>",
        )
    )
    if seuil:
        figure.add_hline(
            y=seuil, line_dash="dot", line_color=theme.AMBER,
            annotation_text="Seuil de sécurité", annotation_position="top left",
        )
    figure.add_hline(y=0, line_color=theme.RED, line_width=1)
    figure.update_yaxes(title_text="MAD")
    theme.plot(figure, height=400)

    theme.section("Détail jour par jour")
    df_jours = io_utils.forecast_dataframe(prevision)
    theme.dataframe(
        theme.style_dataframe(
            df_jours,
            ["Encaissements (MAD)", "Décaissements (MAD)", "Flux net (MAD)", "Trésorerie projetée (MAD)"],
        ),
        height=360,
    )
    colonnes_export = st.columns([1, 1, 3])
    with colonnes_export[0]:
        theme.download_button(
            "Exporter la prévision (CSV)", io_utils.to_csv_bytes(df_jours),
            f"prevision_{today.isoformat()}.csv", "text/csv", "prev_csv",
        )
    with colonnes_export[1]:
        theme.download_button(
            "Exporter la prévision (Excel)", io_utils.to_excel_bytes({"Prévision": df_jours}),
            f"prevision_{today.isoformat()}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "prev_xlsx",
        )

    theme.section("Flux pris en compte dans la prévision")
    if prevision["items"]:
        df_items = io_utils.forecast_items_dataframe(prevision["items"])
        theme.dataframe(
            theme.style_dataframe(df_items, ["Montant (MAD)"]),
            height=min(420, 60 + 35 * len(df_items)),
        )
    else:
        st.info("Aucun flux attendu dans la fenêtre de prévision.")

    hors_fenetre = prevision["items_outside_horizon"]
    if hors_fenetre:
        total_hors = sum(finance.to_decimal(i["amount"]) for i in hors_fenetre)
        st.caption(
            f"{len(hors_fenetre)} flux attendus ({finance.money_str(total_hors, devise)}) se "
            f"trouvent au-delà de l'horizon de {horizon} jours : augmentez l'horizon pour les voir."
        )

    theme.note(
        "<strong>Méthode (prévision = estimation)</strong><br>"
        f"Trésorerie projetée = trésorerie réelle ({finance.money_str(prevision['opening_cash'], devise)}) "
        "+ encaissements attendus - décaissements attendus, jour par jour.<br>"
        "• Seules les opérations au statut « Réalisé » alimentent la trésorerie réelle ; les "
        "opérations « Prévu » et « En retard » n'apparaissent que dans la prévision.<br>"
        "• Une facture déjà représentée par une opération prévue liée n'est pas comptée deux fois.<br>"
        f"• Les factures clients échues sont attendues sous {delai} jour(s) ; les dettes "
        "fournisseurs échues sont considérées comme payables immédiatement.<br>"
        "• Aucune probabilité de paiement n'est modélisée : les montants futurs sont incertains."
    )
