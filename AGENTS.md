# AGENTS.md — Instructions pour intervenir sur CashFlow AI

## Nature du projet

Prototype académique de gestion de trésorerie pour PME marocaines : Python + Streamlit +
SQLite + Pandas + Plotly. Application **locale**, **sans API externe**, **interface en
français**, devise **MAD**.

## Langue et style

* Tout le texte visible par l'utilisateur est en **français** (accents compris).
* Les identifiants de code restent en français métier (`tresorerie`, `previsions`,
  `encaissement`) ou en anglais technique (`settings`, `to_decimal`). Ne pas mélanger
  les deux au sein d'une même couche.
* Pas d'emoji dans l'interface (sauf l'icône de page), pas de titre surdimensionné.
* Les commentaires et docstrings expliquent le *pourquoi* métier, pas la syntaxe.

## Architecture

| Fichier | Rôle | Règle |
|---|---|---|
| `auth.py` | Hachage des codes, validation des identifiants | **Pur** : n'importe ni `db` ni Streamlit ; aucun code en clair |
| `connexion.py` | Écran de connexion / déconnexion | Ne fait aucun calcul financier |
| `finance.py` | Moteur de calcul **pur** | Ne doit JAMAIS importer `db`, ni Streamlit |
| `db.py` | Persistance SQLite | Requêtes **paramétrées** uniquement (`?`) |
| `io_utils.py` | Import/export, DataFrames | Aucun calcul métier |
| `assistant.py` | Assistant à base de règles | Ne fabrique jamais un montant : appelle `finance.py` |
| `demo_data.py` | Jeu fictif | Dates toujours **relatives à aujourd'hui** |
| `theme.py` | CSS, cartes KPI, alertes | Ne contient aucun calcul financier |
| `views/*.py` | Une page = un `render(ctx)` | Lecture via `db`, calculs via `finance` |
| `app.py` | Entrée + connexion + navigation + contexte | Le `ctx` est construit **après** authentification |

## Invariants financiers à ne jamais casser

1. `Réalisé` = impacte la trésorerie réelle. `Prévu` / `En retard` = prévision seulement.
2. Une facture n'est pas un mouvement de trésorerie ; seul son règlement l'est.
3. `Solde restant = total − payé`, jamais négatif, surpaiement refusé.
4. Un règlement = un paiement + **une** transaction réalisée, dans **une** transaction
   SQLite (`with conn:`), sinon rollback complet.
5. Un paiement identique (facture + date + montant) est refusé (anti-doublon).
6. Pas de double comptage : une facture déjà couverte par une opération prévue liée
   (`transactions.invoice_id`) est exclue de la prévision.
7. Montants en `Decimal` (`finance.to_decimal`, `finance.money`), jamais en flottants nus.
8. Toute simulation travaille sur des **copies** : aucune écriture en base.
9. Aucun code d'accès en clair : uniquement un sel + une empreinte PBKDF2
   (`auth.hacher_code`). Ne jamais journaliser un code saisi.

## Conventions techniques

* Les widgets Streamlit portent une `key` explicite (obligatoire dans les boucles/onglets).
* Après une écriture en base : `st.rerun()` pour reconstruire le `ctx` et rafraîchir l'UI.
* Afficher les graphiques avec `theme.plot()`, les tableaux avec `theme.dataframe()`,
  les téléchargements avec `theme.download_button()` (compatibilité de versions).
* Lever `ValueError` avec un message français clair ; les vues affichent `st.error(str(exc))`.
* Les dates sont des `datetime.date` en mémoire et des chaînes ISO `AAAA-MM-JJ` en base
  (`db.parse_date` / `db.fmt_date`).
* Ne pas ajouter de dépendance lourde sans nécessité ; `reportlab` est optionnel
  (`io_utils.HAS_REPORTLAB`).

## Vérifications avant de livrer

```powershell
python -m py_compile app.py db.py finance.py theme.py io_utils.py assistant.py demo_data.py auth.py connexion.py views\*.py
python -m pytest tests -q
```

Le test `tests/test_app_pages.py` exécute réellement `app.py` (base temporaire) : il doit
passer pour l'écran de connexion (accès bloqué, code refusé, code accepté) puis pour les
7 pages, base vide puis base de démonstration.

## Pièges déjà rencontrés

* `use_container_width` est déprécié dans Streamlit récent : passer par `theme.plot()`,
  `theme.dataframe()`, `theme.download_button()` qui utilisent `width="stretch"` avec repli.
* Ne pas passer à la fois `index=` et une valeur pré-remplie dans `st.session_state` pour
  un même widget (avertissement Streamlit) : préremplir l'état **avant** de créer le widget
  et omettre `index`.
* Les clés de widgets d'un formulaire d'édition doivent inclure l'identifiant de l'objet
  édité (`f"modifier_{selection}"`), sinon les valeurs restent figées sur l'ancien objet.
* Les dates de démonstration doivent rester relatives à `date.today()` pour que la
  présentation fonctionne quel que soit le jour.
