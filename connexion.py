"""Page de connexion de CashFlow AI.

L'acces aux donnees et aux pages est refuse tant qu'un utilisateur valide ne
s'est pas authentifie. Le code saisi est compare a une empreinte PBKDF2 :
il n'est jamais stocke ni journalise en clair.
"""

from __future__ import annotations

import time

import streamlit as st

import db
import theme

MAX_TENTATIVES = 5
DUREE_BLOCAGE = 60  # secondes


def _secondes_restantes() -> int:
    fin = float(st.session_state.get("connexion_blocage", 0) or 0)
    return max(0, int(round(fin - time.time())))


def render_login(conn) -> None:
    """Affiche le formulaire de connexion. Ne renvoie rien : la session fait foi."""
    st.markdown(
        '<div class="cf-login-hero">'
        '<div class="cf-login-logo">CashFlow AI</div>'
        '<div class="cf-login-tag">Le copilote intelligent de trésorerie '
        "des PME marocaines</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    _, centre, _ = st.columns([1, 1.15, 1])

    with centre:
        restant = _secondes_restantes()
        bloque = restant > 0

        with st.form("form_connexion"):
            st.markdown(
                '<div class="cf-login-title">Connexion</div>', unsafe_allow_html=True
            )
            nom = st.text_input(
                "Nom d'utilisateur",
                key="connexion_nom",
                placeholder="ex. admin",
                disabled=bloque,
            )
            code = st.text_input(
                "Code d'accès",
                type="password",
                key="connexion_code",
                placeholder="Votre code personnel",
                disabled=bloque,
            )
            valider = st.form_submit_button(
                "Se connecter", type="primary", disabled=bloque
            )

        if valider and not bloque:
            if not nom or not code:
                st.error("Renseignez le nom d'utilisateur et le code d'accès.")
            else:
                utilisateur = db.authenticate(conn, nom, code)
                if utilisateur:
                    st.session_state["utilisateur"] = utilisateur
                    st.session_state["connexion_echecs"] = 0
                    st.session_state["connexion_blocage"] = 0
                    st.session_state.pop("connexion_code", None)
                    st.rerun()
                else:
                    echecs = int(st.session_state.get("connexion_echecs", 0)) + 1
                    if echecs >= MAX_TENTATIVES:
                        st.session_state["connexion_echecs"] = 0
                        st.session_state["connexion_blocage"] = time.time() + DUREE_BLOCAGE
                        st.error(
                            "Trop de tentatives échouées. La connexion est bloquée "
                            f"pendant {DUREE_BLOCAGE} secondes."
                        )
                    else:
                        st.session_state["connexion_echecs"] = echecs
                        st.error(
                            "Nom d'utilisateur ou code d'accès incorrect. "
                            f"Tentative {echecs} sur {MAX_TENTATIVES}."
                        )

        if bloque:
            st.warning(
                f"Connexion temporairement bloquée. Réessayez dans {restant} seconde(s)."
            )

        st.markdown(
            '<div class="cf-login-help">'
            "Accès réservé aux utilisateurs autorisés.<br>"
            "Les codes sont conservés sous forme d'empreinte (PBKDF2-HMAC-SHA256), "
            "jamais en clair.<br>"
            "Application locale — aucune donnée n'est transmise à l'extérieur."
            "</div>",
            unsafe_allow_html=True,
        )


def deconnexion() -> None:
    """Ferme la session en cours et revient a l'ecran de connexion."""
    for cle in ("utilisateur", "connexion_nom", "connexion_code", "connexion_echecs"):
        st.session_state.pop(cle, None)
    st.session_state["connexion_blocage"] = 0
    st.rerun()
