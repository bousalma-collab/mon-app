"""CashFlow AI — Le copilote intelligent de trésorerie des PME marocaines.

Point d'entrée de l'application Streamlit.

Lancement :
    python -m streamlit run app.py
"""

from __future__ import annotations

from datetime import date

import streamlit as st

st.set_page_config(
    page_title="CashFlow AI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

import auth  # noqa: E402
import connexion  # noqa: E402
import db  # noqa: E402
import demo_data  # noqa: E402
import finance  # noqa: E402
import theme  # noqa: E402
from views import assistant_ia, dashboard, factures, previsions, rapports, simulateur, tresorerie  # noqa: E402

PAGES = {
    "Tableau de bord": dashboard.render,
    "Trésorerie": tresorerie.render,
    "Factures": factures.render,
    "Prévisions": previsions.render,
    "Simulateur": simulateur.render,
    "Assistant IA": assistant_ia.render,
    "Rapports et paramètres": rapports.render,
}

HORIZONS = [7, 30, 60, 90]


def _initialiser() -> object:
    try:
        conn = db.get_connection()
        db.init_db(conn)
        db.refresh_transaction_statuses(conn)
        db.refresh_invoice_statuses(conn)
        return conn
    except Exception as exc:  # noqa: BLE001
        st.error(
            "Impossible d'initialiser la base de données locale "
            f"(data/cashflow_ai.db) :\n\n{exc}"
        )
        st.stop()


def _sidebar(ctx: dict) -> str:
    settings = ctx["settings"]
    devise = settings.get("currency") or "MAD"
    utilisateur = st.session_state.get("utilisateur") or {}

    with st.sidebar:
        st.markdown('<div class="cf-brand">CashFlow AI</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="cf-brand-sub">Le copilote intelligent de trésorerie '
            "des PME marocaines</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="cf-side-block"><strong>{settings.get("company_name", "")}</strong>'
            f"<br>Devise : {devise} — base locale SQLite</div>",
            unsafe_allow_html=True,
        )
        if settings.get("demo_mode"):
            st.markdown(
                '<div class="cf-side-block" style="background:#3a2f10;border-color:#7a5f1d">'
                "Mode démonstration actif — données fictives</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div class="cf-who">Connecté : '
            f'<strong>{utilisateur.get("full_name") or utilisateur.get("username") or "—"}</strong>'
            '<br><span style="font-size:.74rem">'
            f'{auth.libelle_role(utilisateur.get("role", "lecteur"))}'
            f' · {utilisateur.get("username", "")}</span></div>',
            unsafe_allow_html=True,
        )

        page = st.radio("Navigation", list(PAGES.keys()), key="nav", label_visibility="collapsed")

        st.markdown("---")
        horizon = st.selectbox(
            "Horizon de prévision",
            HORIZONS,
            index=HORIZONS.index(int(ctx["horizon"])) if int(ctx["horizon"]) in HORIZONS else 1,
            key="horizon",
            format_func=lambda valeur: f"{valeur} jours",
        )

        tresorerie = finance.actual_cash(settings, ctx["transactions"])
        st.markdown(
            '<div class="cf-side-block">'
            f"Trésorerie actuelle<br><strong>{finance.money_str(tresorerie, devise)}</strong>"
            f"<br><span style='font-size:.75rem'>"
            f"{len(ctx['transactions'])} transaction(s) — "
            f"{len(ctx['invoices'])} facture(s)</span></div>",
            unsafe_allow_html=True,
        )

        with st.expander("Données de démonstration"):
            st.caption(
                "Charge la PME fictive Atlas Distribution SARL (historique, factures, "
                "paiements, prévisions) pour illustrer l'application."
            )
            confirmation = st.checkbox(
                "Remplacer les données actuelles", key="side_demo_confirmation"
            )
            if st.button("Charger les données de démonstration", key="side_demo_bouton"):
                if not confirmation:
                    st.error("Cochez la case de confirmation avant de charger la démonstration.")
                else:
                    resume = demo_data.load_demo_data(ctx["conn"], ctx["today"])
                    st.success(
                        f"Données de démonstration chargées : "
                        f"{resume['completed_transactions']} opérations réalisées, "
                        f"{resume['invoices']} factures, {resume['payments']} paiements."
                    )
                    st.rerun()

        st.markdown(
            f'<div class="cf-side-block" style="font-size:.74rem">'
            f"Base : data/cashflow_ai.db<br>Date du jour : "
            f"{finance.format_date_fr(ctx['today'])}<br>"
            "Aucune connexion bancaire ni API externe.</div>",
            unsafe_allow_html=True,
        )

        if st.button("Se déconnecter", key="bouton_deconnexion"):
            connexion.deconnexion()
    return page


def main() -> None:
    theme.inject_css()
    theme.apply_plotly_theme()

    conn = _initialiser()

    # Verrou d'acces : sans utilisateur authentifie, on n'affiche que la connexion.
    if not st.session_state.get("utilisateur"):
        theme.masquer_sidebar()
        connexion.render_login(conn)
        theme.footer()
        return

    settings = db.get_settings(conn)
    today = date.today()
    transactions = db.list_transactions(conn)
    invoices = db.list_invoices(conn)

    ctx = {
        "conn": conn,
        "settings": settings,
        "transactions": transactions,
        "invoices": invoices,
        "today": today,
        "horizon": int(st.session_state.get("horizon", 30)),
        "collection_delay": int(
            st.session_state.get("collection_delay", finance.DEFAULT_COLLECTION_DELAY)
        ),
    }

    page = _sidebar(ctx)
    ctx["horizon"] = int(st.session_state.get("horizon", ctx["horizon"]))
    ctx["collection_delay"] = int(
        st.session_state.get("collection_delay", ctx["collection_delay"])
    )

    PAGES[page](ctx)
    theme.footer()


if __name__ == "__main__":
    main()
