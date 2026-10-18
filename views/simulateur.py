"""Page « Simulateur » : trois scenarios de stress sur la tresorerie.

Aucune simulation ne modifie les donnees stockees : les fonctions de `finance.py`
travaillent sur des copies.
"""

from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go
import streamlit as st

import finance
import theme

CLES_SIMULATION = [
    "simA_cible",
    "simA_delai",
    "simB_pct",
    "simC_date",
    "simC_montant",
    "simC_libelle",
]


def _reinitialiser() -> None:
    for cle in CLES_SIMULATION:
        if cle in st.session_state:
            del st.session_state[cle]
    st.rerun()


def _afficher_comparaison(
    base: dict, scenario: dict, titre: str, description: str, devise: str, seuil: float
) -> None:
    comparaison = finance.compare_forecasts(base, scenario)
    base_kpi = comparaison["base"]
    scen_kpi = comparaison["scenario"]

    st.markdown(f"**{titre}**")
    st.caption(description)
    theme.kpi_row(
        [
            {
                "label": "Trésorerie finale — référence",
                "value": finance.money_str(base_kpi["final_cash"], devise),
                "sub": f"À {base['horizon_days']} jours",
                "tone": "neutral",
            },
            {
                "label": "Trésorerie finale — scénario",
                "value": finance.money_str(scen_kpi["final_cash"], devise),
                "sub": "Résultat hypothétique",
                "tone": "positive" if scen_kpi["final_cash"] >= 0 else "danger",
            },
            {
                "label": "Écart de trésorerie finale",
                "value": finance.money_str(comparaison["final_delta"], devise),
                "sub": "Scénario - référence",
                "tone": "danger" if comparaison["final_delta"] < 0 else "positive",
            },
            {
                "label": "Minimum de trésorerie",
                "value": finance.money_str(scen_kpi["min_cash"], devise),
                "sub": (
                    f"Référence : {finance.money_str(base_kpi['min_cash'], devise)} "
                    f"({finance.money_str(comparaison['min_delta'], devise)})"
                ),
                "tone": "danger" if scen_kpi["min_cash"] < 0 else "warning",
            },
        ]
    )
    theme.kpi_row(
        [
            {
                "label": "Jours sous le seuil — référence",
                "value": str(base_kpi["days_below_threshold"]),
                "sub": f"Seuil {finance.money_str(seuil, devise)}",
                "tone": "neutral",
            },
            {
                "label": "Jours sous le seuil — scénario",
                "value": str(scen_kpi["days_below_threshold"]),
                "sub": f"Écart : {comparaison['extra_days_below_threshold']:+d} jour(s)",
                "tone": "warning" if comparaison["extra_days_below_threshold"] > 0 else "positive",
            },
            {
                "label": "Première trésorerie négative (scénario)",
                "value": (
                    finance.format_date_fr(scen_kpi["first_negative_date"])
                    if scen_kpi["first_negative_date"]
                    else "Aucune"
                ),
                "sub": (
                    "Référence : "
                    + (
                        finance.format_date_fr(base_kpi["first_negative_date"])
                        if base_kpi["first_negative_date"]
                        else "aucune"
                    )
                ),
                "tone": "danger" if scen_kpi["first_negative_date"] else "positive",
            },
            {
                "label": "Pire situation identifiée",
                "value": finance.money_str(comparaison["worst_case_min"], devise),
                "sub": "Minimum le plus bas des deux courbes",
                "tone": "danger" if comparaison["worst_case_min"] < 0 else "warning",
            },
        ]
    )

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[j["date"] for j in base["days"]],
            y=[j["closing"] for j in base["days"]],
            name="Référence",
            mode="lines",
            line=dict(color=theme.BLUE, width=2.4),
            hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.2f} MAD<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[j["date"] for j in scenario["days"]],
            y=[j["closing"] for j in scenario["days"]],
            name="Scénario (hypothèse)",
            mode="lines",
            line=dict(color=theme.RED, width=2.4, dash="dash"),
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
    theme.plot(figure, height=370)

    ecarts = []
    for index, jour in enumerate(scenario["days"]):
        reference = base["days"][index]["closing"] if index < len(base["days"]) else 0.0
        ecarts.append(jour["closing"] - reference)
    figure_ecart = go.Figure(
        go.Bar(
            x=[j["date"] for j in scenario["days"]],
            y=ecarts,
            name="Écart de trésorerie",
            marker_color=[theme.RED if valeur < 0 else theme.GREEN for valeur in ecarts],
            hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.2f} MAD<extra></extra>",
        )
    )
    figure_ecart.update_layout(title="Écart de trésorerie par rapport à la référence (MAD)")
    theme.plot(figure_ecart, height=280)

    theme.note(
        "<strong>Résultat hypothétique.</strong> Aucune donnée enregistrée (transaction ou "
        "facture) n'a été modifiée : la simulation recalcule une prévision sur des copies. "
        "Les montants futurs restent incertains."
    )


def render(ctx: dict) -> None:
    settings = ctx["settings"]
    transactions = ctx["transactions"]
    factures = ctx["invoices"]
    today = ctx["today"]
    devise = settings.get("currency") or "MAD"
    horizon = int(ctx["horizon"])
    delai = int(ctx["collection_delay"])
    seuil = settings.get("min_cash_threshold") or 0

    base = finance.build_forecast(settings, transactions, factures, today, horizon, delai)

    theme.page_title(
        "Simulateur de scénarios",
        "Testez trois chocs de trésorerie et comparez-les à la prévision de référence. "
        "Les simulations sont hypothétiques et ne modifient jamais vos données.",
    )
    theme.demo_banner(bool(settings.get("demo_mode")), settings.get("company_name", ""))

    colonnes = st.columns([1.2, 2.6, 1.6])
    with colonnes[0]:
        st.markdown(
            theme.kpi_card("Horizon simulé", f"{horizon} jours", "Barre latérale", "info"),
            unsafe_allow_html=True,
        )
    with colonnes[1]:
        st.markdown(
            theme.kpi_card(
                "Trésorerie de référence",
                finance.money_str(base["opening_cash"], devise),
                f"Minimum projeté : {finance.money_str(finance.forecast_kpis(base)['min_cash'], devise)} "
                f"le {finance.format_date_fr(finance.forecast_kpis(base)['min_cash_date'])}",
                "neutral",
            ),
            unsafe_allow_html=True,
        )
    with colonnes[2]:
        if st.button("Réinitialiser les simulations", key="sim_reset"):
            _reinitialiser()

    onglet_a, onglet_b, onglet_c = st.tabs(
        [
            "Scénario A — Retard de paiement client",
            "Scénario B — Hausse des dépenses",
            "Scénario C — Dépense exceptionnelle",
        ]
    )

    # ------------------------------------------------------- Scénario A
    with onglet_a:
        entrees = [it for it in base["items"] if it["direction"] == "in"]
        if not entrees:
            st.info(
                "Aucun encaissement attendu dans l'horizon choisi : le scénario A n'est pas "
                "applicable. Augmentez l'horizon ou ajoutez des opérations prévues."
            )
        else:
            position_par_defaut = max(
                range(len(entrees)), key=lambda i: entrees[i]["amount"]
            )

            def _etiquette(index: int) -> str:
                item = entrees[min(index, len(entrees) - 1)]
                return (
                    f"{finance.format_date_fr(item['date'])} — {item['label']} "
                    f"({item['party'] or 'tiers non précisé'}) — "
                    f"{finance.money_str(item['amount'], devise)}"
                )

            options_cible = list(range(len(entrees)))
            if st.session_state.get("simA_cible") not in options_cible:
                st.session_state["simA_cible"] = position_par_defaut
            index_cible = st.selectbox(
                "Encaissement à retarder",
                options=options_cible,
                format_func=_etiquette,
                key="simA_cible",
            )
            cible = entrees[min(index_cible, len(entrees) - 1)]
            retard = st.slider(
                "Retard appliqué (jours)", min_value=1, max_value=30, value=15, key="simA_delai"
            )
            nouvelles_tx, nouvelles_factures = finance.delay_item(
                transactions, factures, cible, retard
            )
            scenario = finance.build_forecast(
                settings, nouvelles_tx, nouvelles_factures, today, horizon, delai
            )
            _afficher_comparaison(
                base,
                scenario,
                f"Hypothèse : « {cible['label']} » payé {retard} jours plus tard",
                "Le montant attendu de "
                f"{finance.money_str(cible['amount'], devise)} est décalé du "
                f"{finance.format_date_fr(cible['date'])} au "
                f"{finance.format_date_fr(cible['date'] + timedelta(days=retard))}.",
                devise,
                seuil,
            )

    # ------------------------------------------------------- Scénario B
    with onglet_b:
        pourcentage = st.slider(
            "Hausse appliquée aux décaissements prévus (%)",
            min_value=1,
            max_value=50,
            value=10,
            key="simB_pct",
        )
        transactions_augmentees = finance.scale_planned_expenses(transactions, pourcentage)
        scenario = finance.build_forecast(
            settings, transactions_augmentees, factures, today, horizon, delai
        )
        sorties_prevues = sum(
            finance.to_decimal(tx["amount"])
            for tx in transactions
            if not finance.is_actual(tx) and tx["type"] == "Décaissement"
        )
        sorties_scenario = sorties_prevues * (
            finance.to_decimal(1) + finance.to_decimal(pourcentage) / finance.to_decimal(100)
        )
        _afficher_comparaison(
            base,
            scenario,
            f"Hypothèse : +{pourcentage} % sur les décaissements prévus",
            "Les décaissements prévus passent de "
            f"{finance.money_str(sorties_prevues, devise)} à "
            f"{finance.money_str(sorties_scenario, devise)}.",
            devise,
            seuil,
        )

    # ------------------------------------------------------- Scénario C
    with onglet_c:
        colonnes = st.columns(3)
        with colonnes[0]:
            date_depense = st.date_input(
                "Date de la dépense",
                value=today + timedelta(days=10),
                key="simC_date",
            )
        with colonnes[1]:
            montant = st.number_input(
                "Montant de la dépense (MAD)",
                min_value=0.0,
                value=100000.0,
                step=10000.0,
                format="%.2f",
                key="simC_montant",
            )
        with colonnes[2]:
            libelle = st.text_input(
                "Libellé", value="Dépense exceptionnelle (simulation)", key="simC_libelle"
            )
        transactions_extra = finance.add_planned_expense(
            transactions, date_depense, montant, libelle
        )
        scenario = finance.build_forecast(
            settings, transactions_extra, factures, today, horizon, delai
        )
        _afficher_comparaison(
            base,
            scenario,
            f"Hypothèse : dépense exceptionnelle de {finance.money_str(montant, devise)} "
            f"le {finance.format_date_fr(date_depense)}",
            f"Dépense « {libelle} » ajoutée uniquement dans la simulation.",
            devise,
            seuil,
        )
