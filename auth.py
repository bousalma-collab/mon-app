"""Authentification locale de CashFlow AI.

Aucun code d'acces n'est stocke en clair : on conserve un sel aleatoire et une
empreinte PBKDF2-HMAC-SHA256. Ce module est volontairement pur (aucune
dependance a SQLite ni a Streamlit) afin de rester testable isolement.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

# Cout de derivation : eleve a dessein pour ralentir une attaque par force brute.
ITERATIONS = 200_000
LONGUEUR_SEL = 16
LONGUEUR_CODE_MIN = 6
LONGUEUR_NOM_MAX = 32

ROLES = ("admin", "lecteur")
ROLE_LABELS = {"admin": "Administrateur", "lecteur": "Consultation"}

MOTIF_NOM = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,30}[a-z0-9])?$")

# Comptes crees au premier lancement (modifiables dans l'application).
UTILISATEURS_DEFAUT = (
    {
        "username": "admin",
        "full_name": "Administrateur",
        "role": "admin",
        "code": "cashflow2026",
    },
    {
        "username": "demo",
        "full_name": "Compte de démonstration",
        "role": "lecteur",
        "code": "demo2026",
    },
)


def generer_sel() -> str:
    """Renvoie un sel aleatoire hexadecimal, different pour chaque compte."""
    return secrets.token_hex(LONGUEUR_SEL)


def hacher_code(code: str, sel: str) -> str:
    """Calcule l'empreinte PBKDF2 d'un code d'acces pour un sel donne."""
    if not isinstance(code, str) or not code:
        raise ValueError("Le code d'accès est obligatoire.")
    return hashlib.pbkdf2_hmac(
        "sha256", code.encode("utf-8"), bytes.fromhex(sel), ITERATIONS
    ).hex()


def verifier_code(code: str, sel: str, empreinte: str) -> bool:
    """Compare un code saisi a l'empreinte stockee, en temps constant."""
    if not code or not sel or not empreinte:
        return False
    try:
        candidat = hacher_code(code, sel)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidat, empreinte)


def normaliser_username(valeur: str) -> str:
    """Valide et normalise un nom d'utilisateur (minuscules, sans espaces)."""
    nom = (valeur or "").strip().lower()
    if not nom:
        raise ValueError("Le nom d'utilisateur est obligatoire.")
    if len(nom) > LONGUEUR_NOM_MAX:
        raise ValueError(
            f"Le nom d'utilisateur ne doit pas dépasser {LONGUEUR_NOM_MAX} caractères."
        )
    if not MOTIF_NOM.match(nom):
        raise ValueError(
            "Le nom d'utilisateur ne peut contenir que des lettres non accentuées, "
            "des chiffres, '.', '_' ou '-', et doit commencer par une lettre ou un chiffre."
        )
    return nom


def valider_code(code: str) -> str:
    """Verifie la longueur minimale et l'absence d'espaces de bord."""
    valeur = code or ""
    if len(valeur) < LONGUEUR_CODE_MIN:
        raise ValueError(
            f"Le code d'accès doit contenir au moins {LONGUEUR_CODE_MIN} caractères."
        )
    if valeur != valeur.strip():
        raise ValueError(
            "Le code d'accès ne doit pas commencer ou se terminer par un espace."
        )
    return valeur


def valider_role(role: str) -> str:
    valeur = (role or "").strip().lower()
    if valeur not in ROLES:
        raise ValueError("Rôle invalide : choisissez « Administrateur » ou « Consultation ».")
    return valeur


def libelle_role(role: str) -> str:
    return ROLE_LABELS.get(role, "Consultation")
