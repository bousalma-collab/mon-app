"""Page « Assistant IA » : assistant financier local a base de regles."""

from __future__ import annotations

import streamlit as st

import assistant
import finance
import theme


def _contexte(ctx: dict) -> dict:
    return {
        "settings": ctx["settings"],
        "transactions": ctx["transactions"],
        "invoices": ctx["invoices"],
        "today": ctx["today"],
        "horizon_days": ctx["horizon"],
        "collection_delay": ctx["collection_delay"],
    }


def _ajouter_question(question: str, ctx: dict) -> None:
    st.session_state.chat.append({"role": "user", "texte": question})
    try:
        reponse = assistant.repondre(question, _contexte(ctx))
    except Exception as exc:  # noqa: BLE001
        reponse = {
            "titre": "Analyse impossible",
            "reponse": (
                "Une erreur est survenue pendant le calcul : les données sont peut-être "
                f"incomplètes.\n\n`{exc}`"
            ),
            "donnees": [],
            "periode": "-",
            "source": "erreur",
        }
    st.session_state.chat.append({"role": "assistant", **reponse})


def _afficher_message(message: dict) -> None:
    role = message.get("role", "assistant")
    with st.chat_message("user" if role == "user" else "assistant"):
        if role == "user":
            st.markdown(message.get("texte", ""))
            return
        titre = message.get("titre")
        if titre:
            st.markdown(f"#### {titre}")
        st.markdown(message.get("reponse", ""))
        donnees = message.get("donnees") or []
        if donnees:
            cartes = [
                {"label": label, "value": str(valeur), "tone": "neutral"}
                for label, valeur in donnees
            ]
            theme.kpi_row(cartes, colonnes_par_ligne=4)
        pied = []
        if message.get("periode"):
            pied.append(f"Période analysée : {message['periode']}")
        if message.get("source"):
            pied.append(f"Calcul : {message['source']}")
        if pied:
            st.caption(" • ".join(pied))


def render(ctx: dict) -> None:
    settings = ctx["settings"]
    devise = settings.get("currency") or "MAD"

    theme.page_title(
        "Assistant IA",
        "Assistant financier local : il répond avec les chiffres réels de votre "
        "application, sans clé d'API et sans connexion à un modèle externe.",
    )
    theme.demo_banner(bool(settings.get("demo_mode")), settings.get("company_name", ""))
    theme.note(
        "<strong>Transparence technique :</strong> cet assistant est un moteur de règles "
        "déterministe exécuté en local. Il ne s'agit pas d'un grand modèle de langage : il "
        "reconnaît une série de questions prévues, appelle les fonctions de calcul de "
        "CashFlow AI et restitue les montants, la période analysée et la méthode. "
        "L'architecture est prête pour un futur fournisseur d'IA optionnel."
    )

    if "chat" not in st.session_state:
        st.session_state.chat = [
            {
                "role": "assistant",
                "titre": "Bonjour",
                "reponse": (
                    "Je suis l'assistant financier **local** de CashFlow AI. Je peux vous "
                    f"renseigner sur votre trésorerie réelle ({devise}), vos factures en "
                    "retard, les paiements à prévoir, votre flux net et vos risques de "
                    "liquidité. Choisissez une question ci-dessous ou écrivez la vôtre."
                ),
                "donnees": [],
                "periode": f"Aujourd'hui : {finance.format_date_fr(ctx['today'])}",
                "source": "assistant local (règles)",
            }
        ]

    for message in st.session_state.chat:
        _afficher_message(message)

    theme.section("Questions suggérées")
    colonnes = st.columns(2)
    for index, question in enumerate(assistant.SUGGESTIONS):
        with colonnes[index % 2]:
            if st.button(question, key=f"assist_{index}"):
                _ajouter_question(question, ctx)
                st.rerun()

    question_libre = st.chat_input("Posez votre question sur la trésorerie…")
    if question_libre:
        _ajouter_question(question_libre, ctx)
        st.rerun()

    if st.button("Effacer la conversation", key="assist_clear"):
        st.session_state.chat = st.session_state.chat[:1]
        st.rerun()
