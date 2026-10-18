"""Habillage graphique de CashFlow AI (CSS, cartes KPI, alertes, graphiques)."""

from __future__ import annotations

from typing import Optional

import plotly.graph_objects as go
import streamlit as st

NAVY = "#0f2038"
NAVY_LIGHT = "#1c3a5e"
BACKGROUND = "#f5f7fb"
CARD_BORDER = "#e2e8f2"
GREEN = "#12876f"
RED = "#c0392b"
AMBER = "#c9820f"
BLUE = "#2563a8"
GREY = "#5b6b82"

TONE_COLORS = {
    "positive": GREEN,
    "danger": RED,
    "warning": AMBER,
    "info": BLUE,
    "neutral": NAVY,
}

PLOTLY_COLORWAY = [BLUE, GREEN, RED, AMBER, "#7d5ba6", "#3d8b8b", GREY]

CSS = f"""
<style>
    .stApp {{
        background: {BACKGROUND};
    }}
    html, body, [class*="css"] {{
        font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    }}
    .block-container {{
        padding-top: 2.6rem;
        padding-bottom: 3rem;
        max-width: 1500px;
    }}
    /* ------- En-tete Streamlit neutralise ------- */
    [data-testid="stHeader"] {{
        background: transparent;
    }}
    [data-testid="stToolbar"] {{
        display: none;
    }}
    [data-testid="stDecoration"] {{
        display: none;
    }}
    footer {{
        visibility: hidden;
    }}
    /* ------- Barre laterale ------- */
    [data-testid="stSidebar"] {{
        background: {NAVY};
        border-right: 1px solid #0a1828;
    }}
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span {{
        color: #eaf1fa;
    }}
    [data-testid="stSidebar"] .cf-brand {{
        font-size: 1.32rem;
        font-weight: 700;
        color: #ffffff;
        letter-spacing: .2px;
    }}
    [data-testid="stSidebar"] .cf-brand-sub {{
        font-size: .78rem;
        color: #8fb0d4;
        line-height: 1.35;
        margin-bottom: 6px;
    }}
    [data-testid="stSidebar"] .cf-side-block {{
        background: rgba(255,255,255,.06);
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 10px;
        padding: 10px 12px;
        margin: 8px 0;
        font-size: .82rem;
        color: #dfe9f5;
    }}
    [data-testid="stSidebar"] .cf-side-block strong {{ color: #ffffff; }}
    [data-testid="stSidebar"] [role="radiogroup"] label {{
        padding: 6px 8px;
        border-radius: 8px;
    }}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {{
        background: rgba(255,255,255,.08);
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] *,
    [data-testid="stSidebar"] input {{
        color: #0f2038 !important;
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] {{
        background: #ffffff;
        border-radius: 8px;
    }}
    /* ------- Titres de page ------- */
    .cf-page-title {{
        font-size: 1.62rem;
        font-weight: 700;
        color: {NAVY};
        margin-bottom: 2px;
    }}
    .cf-page-sub {{
        color: {GREY};
        font-size: .92rem;
        margin-bottom: 14px;
    }}
    .cf-section {{
        font-size: 1.05rem;
        font-weight: 650;
        color: {NAVY};
        margin: 14px 0 6px 0;
        padding-bottom: 4px;
        border-bottom: 2px solid #e7edf6;
    }}
    /* ------- Cartes KPI ------- */
    .cf-kpi {{
        background: #ffffff;
        border: 1px solid {CARD_BORDER};
        border-left: 4px solid {NAVY};
        border-radius: 12px;
        padding: 14px 16px;
        box-shadow: 0 1px 3px rgba(15,32,56,.06);
        height: 100%;
        margin-bottom: 10px;
    }}
    .cf-kpi.positive {{ border-left-color: {GREEN}; }}
    .cf-kpi.danger   {{ border-left-color: {RED}; }}
    .cf-kpi.warning  {{ border-left-color: {AMBER}; }}
    .cf-kpi.info     {{ border-left-color: {BLUE}; }}
    .cf-kpi-label {{
        font-size: .78rem;
        text-transform: uppercase;
        letter-spacing: .45px;
        color: {GREY};
        font-weight: 600;
    }}
    .cf-kpi-value {{
        font-size: 1.36rem;
        font-weight: 700;
        color: {NAVY};
        margin-top: 4px;
        line-height: 1.25;
    }}
    .cf-kpi-value.positive {{ color: {GREEN}; }}
    .cf-kpi-value.danger   {{ color: {RED}; }}
    .cf-kpi-value.warning  {{ color: {AMBER}; }}
    .cf-kpi-sub {{
        font-size: .76rem;
        color: {GREY};
        margin-top: 4px;
    }}
    /* ------- Alertes ------- */
    .cf-alert {{
        border-radius: 10px;
        padding: 11px 14px;
        margin-bottom: 9px;
        border: 1px solid {CARD_BORDER};
        background: #ffffff;
        border-left-width: 5px;
    }}
    .cf-alert .cf-alert-title {{
        font-weight: 650;
        color: {NAVY};
        font-size: .93rem;
    }}
    .cf-alert .cf-alert-msg {{
        color: #38465c;
        font-size: .86rem;
        margin-top: 2px;
    }}
    .cf-alert.danger  {{ border-left-color: {RED}; background: #fdf3f2; }}
    .cf-alert.warning {{ border-left-color: {AMBER}; background: #fdf8ef; }}
    .cf-alert.info    {{ border-left-color: {BLUE}; background: #f2f7fd; }}
    .cf-alert.success {{ border-left-color: {GREEN}; background: #f1f9f6; }}
    /* ------- Badges ------- */
    .cf-badge {{
        display: inline-block;
        padding: 2px 9px;
        border-radius: 999px;
        font-size: .74rem;
        font-weight: 650;
        border: 1px solid transparent;
    }}
    .cf-badge.green  {{ background: #e6f5f0; color: {GREEN}; border-color: #b8e0d5; }}
    .cf-badge.red    {{ background: #fbeaea; color: {RED};   border-color: #f0c3bf; }}
    .cf-badge.amber  {{ background: #fdf3e3; color: {AMBER}; border-color: #f0dcb4; }}
    .cf-badge.blue   {{ background: #eaf2fb; color: {BLUE};  border-color: #c3d9f0; }}
    .cf-badge.grey   {{ background: #eef1f6; color: {GREY};  border-color: #d9e0ea; }}
    .cf-demo {{
        background: #fff6e5;
        border: 1px dashed #e0a83c;
        color: #8a5a06;
        border-radius: 8px;
        padding: 7px 11px;
        font-size: .82rem;
        margin-bottom: 12px;
    }}
    .cf-note {{
        background: #f4f7fc;
        border: 1px solid {CARD_BORDER};
        border-radius: 10px;
        padding: 10px 13px;
        color: #3b4a60;
        font-size: .85rem;
    }}
    .cf-footer {{
        color: {GREY};
        font-size: .76rem;
        text-align: center;
        margin-top: 26px;
    }}
    div[data-testid="stMetricValue"] {{ font-size: 1.3rem; }}
    .stTabs [data-baseweb="tab"] {{ font-weight: 600; }}
    [data-testid="stDataFrame"] {{ border: 1px solid {CARD_BORDER}; border-radius: 10px; }}
    /* ------- Adaptation aux ecrans etroits ------- */
    @media (max-width: 1350px) {{
        .cf-kpi-value {{ font-size: 1.16rem; }}
        .cf-kpi-label {{ font-size: .72rem; }}
        .cf-kpi {{ padding: 12px 13px; }}
        .cf-kpi-sub {{ font-size: .72rem; }}
        .block-container {{ padding-left: 1.2rem; padding-right: 1.2rem; }}
    }}
    @media (max-width: 900px) {{
        .cf-kpi-value {{ font-size: 1.05rem; }}
        .cf-page-title {{ font-size: 1.3rem; }}
        .cf-kpi {{ padding: 10px 11px; }}
    }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def apply_plotly_theme() -> None:
    """Theme Plotly homogene pour tous les graphiques."""
    import plotly.io as pio

    template = go.layout.Template()
    template.layout = go.Layout(
        colorway=PLOTLY_COLORWAY,
        font=dict(family='Inter, "Segoe UI", Arial', size=12, color=NAVY),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis=dict(gridcolor="#e8eef7", zerolinecolor="#cfd9e6"),
        yaxis=dict(gridcolor="#e8eef7", zerolinecolor="#cfd9e6"),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    pio.templates["cashflow"] = template
    pio.templates.default = "cashflow"


def plot(figure: go.Figure, height: Optional[int] = None) -> None:
    """Affiche un graphique Plotly (compatible anciennes et nouvelles versions)."""
    if height:
        figure.update_layout(height=height)
    try:
        st.plotly_chart(figure, width="stretch")
    except TypeError:
        st.plotly_chart(figure, use_container_width=True)


def dataframe(donnees, **kwargs):
    """Affiche un tableau (compatible anciennes et nouvelles versions)."""
    try:
        return st.dataframe(donnees, width="stretch", **kwargs)
    except TypeError:
        return st.dataframe(donnees, use_container_width=True, **kwargs)


def download_button(label: str, donnees, fichier: str, mime: str, key: str) -> None:
    """Bouton de telechargement (compatible anciennes et nouvelles versions)."""
    try:
        st.download_button(
            label, donnees, file_name=fichier, mime=mime, key=key, width="stretch"
        )
    except TypeError:
        st.download_button(
            label, donnees, file_name=fichier, mime=mime, key=key, use_container_width=True
        )


def page_title(titre: str, sous_titre: str = "") -> None:
    st.markdown(f'<div class="cf-page-title">{titre}</div>', unsafe_allow_html=True)
    if sous_titre:
        st.markdown(f'<div class="cf-page-sub">{sous_titre}</div>', unsafe_allow_html=True)


def section(titre: str) -> None:
    st.markdown(f'<div class="cf-section">{titre}</div>', unsafe_allow_html=True)


def kpi_card(
    label: str,
    value: str,
    sub: str = "",
    tone: str = "neutral",
) -> str:
    tone_classe = tone if tone in TONE_COLORS else "neutral"
    valeur_classe = tone if tone in ("positive", "danger", "warning") else ""
    sous_titre = f'<div class="cf-kpi-sub">{sub}</div>' if sub else ""
    # On garde le montant et la devise sur la même ligne (espace insecable)
    valeur_html = str(value).replace(" ", "\u00a0") if "MAD" in str(value) else str(value)
    return (
        f'<div class="cf-kpi {tone_classe}">'
        f'<div class="cf-kpi-label">{label}</div>'
        f'<div class="cf-kpi-value {valeur_classe}">{valeur_html}</div>'
        f"{sous_titre}</div>"
    )


def kpi_row(cartes: list[dict], colonnes_par_ligne: int = 4) -> None:
    """Affiche une liste de cartes KPI sur une ou plusieurs lignes."""
    for debut in range(0, len(cartes), colonnes_par_ligne):
        groupe = cartes[debut : debut + colonnes_par_ligne]
        colonnes = st.columns(len(groupe))
        for colonne, carte in zip(colonnes, groupe):
            with colonne:
                st.markdown(
                    kpi_card(
                        carte.get("label", ""),
                        carte.get("value", ""),
                        carte.get("sub", ""),
                        carte.get("tone", "neutral"),
                    ),
                    unsafe_allow_html=True,
                )


def alert_card(level: str, titre: str, message: str) -> str:
    niveau = level if level in ("danger", "warning", "info", "success") else "info"
    return (
        f'<div class="cf-alert {niveau}">'
        f'<div class="cf-alert-title">{titre}</div>'
        f'<div class="cf-alert-msg">{message}</div>'
        f"</div>"
    )


def render_alerts(alertes: list[dict], colonnes: int = 2) -> None:
    if not alertes:
        return
    for debut in range(0, len(alertes), colonnes):
        groupe = alertes[debut : debut + colonnes]
        cols = st.columns(len(groupe))
        for colonne, alerte in zip(cols, groupe):
            with colonne:
                st.markdown(
                    alert_card(alerte["level"], alerte["title"], alerte["message"]),
                    unsafe_allow_html=True,
                )


def badge(texte: str, couleur: str = "grey") -> str:
    return f'<span class="cf-badge {couleur}">{texte}</span>'


def statut_badge(statut: str) -> str:
    correspondance = {
        "Réalisé": "green",
        "Payée": "green",
        "Prévu": "blue",
        "Ouverte": "blue",
        "Partiellement payée": "amber",
        "En retard": "red",
    }
    return badge(statut, correspondance.get(statut, "grey"))


def demo_banner(actif: bool, company: str) -> None:
    if actif:
        st.markdown(
            '<div class="cf-demo"><strong>Mode démonstration actif</strong> — les données '
            f"affichées (entreprise « {company} ») sont <strong>fictives</strong> et servent "
            "uniquement à illustrer le fonctionnement de CashFlow AI.</div>",
            unsafe_allow_html=True,
        )


def note(texte: str) -> None:
    st.markdown(f'<div class="cf-note">{texte}</div>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown(
        '<div class="cf-footer">CashFlow AI — prototype académique (Fintech & IA appliquée) '
        "— assistant local à base de règles, aucune connexion bancaire réelle.</div>",
        unsafe_allow_html=True,
    )


def style_dataframe(df, colonnes_montant: Optional[list[str]] = None):
    """Applique un format lisible (montants, dates, lignes en retard) a un DataFrame."""

    def _ligne(row):
        styles = []
        statut = str(row.get("Statut", ""))
        fond = ""
        if statut in ("En retard",):
            fond = "background-color: #fdf0ef"
        elif statut in ("Payée", "Réalisé"):
            fond = "background-color: #f3faf7"
        for colonne in row.index:
            style = fond
            if colonne in (colonnes_montant or []) and isinstance(row[colonne], (int, float)):
                style += " text-align: right;"
            styles.append(style)
        return styles

    return df.style.apply(_ligne, axis=1).hide(axis="index")


def line_chart(
    x,
    y,
    nom: str,
    couleur: str = BLUE,
    seuil: Optional[float] = None,
    remplissage: Optional[str] = None,
) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=x,
            y=y,
            name=nom,
            mode="lines",
            line=dict(color=couleur, width=2.4),
            fill="tozeroy" if remplissage else None,
            fillcolor=remplissage,
            hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.2f} MAD<extra></extra>",
        )
    )
    if seuil:
        figure.add_hline(
            y=seuil,
            line_dash="dot",
            line_color=AMBER,
            annotation_text=f"Seuil {seuil:,.0f} MAD".replace(",", " "),
            annotation_position="top left",
        )
    return figure
