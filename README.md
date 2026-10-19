# CashFlow AI — Le copilote intelligent de trésorerie des PME marocaines

**Anticipez vos flux. Comprenez vos risques. Décidez avec confiance.**

CashFlow AI est un prototype d'application de gestion de trésorerie destiné aux PME
marocaines. Il suit les encaissements et décaissements réels, gère les factures clients
et fournisseurs avec paiements partiels, projette la trésorerie sur 7 à 90 jours,
simule trois scénarios de crise et répond à des questions financières en français.

* Application **100 % locale** : Python + Streamlit + SQLite.
* Aucune connexion bancaire, aucune clé d'API, aucune donnée envoyée sur Internet.
* Devise : **MAD** (dirham marocain). Interface : **français**.
* L'assistant est un **moteur de règles local** (pas un grand modèle de langage).

---

## 1. Fonctionnalités

| Page | Contenu |
|---|---|
| **Connexion** | Écran d'accès par nom d'utilisateur et code personnel ; blocage temporaire après 5 échecs ; déconnexion depuis la barre latérale |
| **Tableau de bord** | 7 indicateurs clés, alertes de risque réelles, 3 graphiques (trésorerie historique, encaissements/décaissements mensuels, trésorerie projetée), dernières opérations, factures en retard |
| **Trésorerie** | Création, modification, suppression (avec confirmation), recherche et filtres, import CSV/Excel, export CSV/Excel |
| **Factures** | Factures clients et fournisseurs, paiements partiels et totaux, statuts (Ouverte, Partiellement payée, En retard, Payée), suppression sécurisée |
| **Prévisions** | Prévision journalière déterministe sur 7, 30, 60 ou 90 jours : encaissements attendus, décaissements attendus, solde projeté, minimum projeté, première date négative, jours sous le seuil |
| **Simulateur** | Scénario A : retard d'un encaissement client (1 à 30 jours) — Scénario B : hausse des dépenses prévues (1 à 50 %) — Scénario C : dépense exceptionnelle. Comparaison graphique avec la référence |
| **Assistant IA** | Assistant financier local en français : situation de trésorerie, factures en retard, paiements à prévoir, flux net, risque de liquidité, simulations |
| **Rapports et paramètres** | Synthèse par période, exports CSV / Excel / PDF, paramètres de l'entreprise, chargement des données de démonstration, effacement des données |

### Règles financières appliquées

* Seules les opérations au statut **Réalisé** comptent dans la trésorerie réelle.
* Les opérations **Prévu** et **En retard** n'alimentent que les prévisions.
* Une facture n'est **jamais** un mouvement de trésorerie : seul son règlement l'est.
* `Solde restant = montant total − montant payé` (jamais négatif, pas de surpaiement).
* Un règlement crée **exactement une** transaction réalisée, dans une transaction SQLite
  atomique (rollback complet en cas d'erreur).
* Un paiement strictement identique (même facture, même date, même montant) est refusé :
  protection contre les doublons.
* **Pas de double comptage** : si une facture est déjà représentée par une opération prévue
  liée (`invoice_id`), la facture est ignorée dans la prévision.
* Trésorerie projetée = trésorerie réelle + encaissements attendus − décaissements attendus.
* Les factures clients échues sont attendues sous un délai de recouvrement paramétrable
  (7 jours par défaut) ; les dettes fournisseurs échues sont supposées payables
  immédiatement (hypothèse prudente).
* Montants calculés en `Decimal` : pas d'erreur d'arrondi.

### Connexion

L'application s'ouvre sur un écran de connexion : sans nom d'utilisateur et code
valides, aucune page ni aucune donnée n'est accessible. Deux comptes sont créés
automatiquement au premier lancement :

| Identifiant | Code d'accès | Rôle |
|---|---|---|
| `admin` | `cashflow2026` | Administrateur — peut gérer les comptes |
| `demo` | `demo2026` | Consultation — accès en lecture |

* Les codes ne sont **jamais stockés en clair** : seule une empreinte
  PBKDF2-HMAC-SHA256 (200 000 itérations, sel aléatoire par compte) est conservée.
* Après **5 tentatives échouées**, la connexion est bloquée pendant 60 secondes.
* La page « Rapports et paramètres » permet de changer son code, de créer des
  comptes, de les désactiver, de réinitialiser un code ou de les supprimer.
* Le dernier administrateur actif ne peut être ni supprimé ni désactivé.

> **Changez les codes par défaut dès la première utilisation**
> (« Rapports et paramètres » → « Mon compte »).

---

## 2. Installation sur Windows

### Prérequis
* Windows 10/11
* Python 3.9 ou plus récent ([python.org](https://www.python.org/downloads/windows/)) —
  cochez **« Add python.exe to PATH »** pendant l'installation.

### Installation des dépendances (PowerShell)

Ouvrez PowerShell dans le dossier du projet, puis :

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Si la commande `python` n'est pas reconnue, essayez `py -3` à la place de `python`.
(La version de Python livrée avec Thonny fonctionne aussi, via son chemin complet.)

### Lancement de l'application

```powershell
python -m streamlit run app.py
```

L'application s'ouvre automatiquement sur <http://localhost:8501>.
Pour l'arrêter : `Ctrl + C` dans la fenêtre PowerShell.

*Raccourci pratique* : double-cliquez sur **`lancer.bat`** — il cherche Python, installe
les dépendances manquantes si besoin et démarre l'application.

---

## 3. Chargement des données de démonstration

Deux possibilités, au choix :

1. **Barre latérale** → ouvrez l'encadré « Données de démonstration », cochez
   « Remplacer les données actuelles », puis cliquez sur
   **« Charger les données de démonstration »**.
2. **Page « Rapports et paramètres »** → section « Données de démonstration ».

Le jeu de démonstration décrit la PME **fictive *Atlas Distribution SARL*** (MAD) :
historique de 4 mois, 12 factures (6 clients / 6 fournisseurs), 7 règlements dont des
paiements partiels, une facture client en retard, 13 opérations prévues et une tension
de trésorerie visible à 3 semaines.

> Les données de démonstration sont **fictives**. Le chargement remplace les données
> existantes : il demande toujours une confirmation explicite et n'est jamais déclenché
> automatiquement au rechargement d'une page.

---

## 4. Lancer les tests

```powershell
python -m pytest tests -q
```

Le dossier `tests/` contient :

* `test_finance.py` : 27 tests des calculs financiers (trésorerie réelle, flux net,
  exclusion des opérations prévues, solde de facture, paiements partiels et totaux,
  détection des retards, prévision journalière, alertes, simulations, refus de
  surpaiement, refus de doublon, absence de double comptage, jeu de démonstration,
  exports…).
* `test_auth.py` : 23 tests de l'authentification (empreintes différentes pour un même
  code, vérification, validation des identifiants, refus d'un mauvais code, compte
  désactivé, doublon de nom, changement de code, protection du dernier administrateur,
  code jamais stocké en clair).
* `test_app_pages.py` : tests d'intégration qui exécutent réellement l'application
  Streamlit (base vide **et** base de démonstration), vérifient que l'écran de connexion
  bloque l'accès, qu'un code refusé laisse la session fermée, qu'un code valide l'ouvre,
  puis que les 7 pages s'affichent sans erreur.

---

## 5. Base de données

* Fichier SQLite : **`data/cashflow_ai.db`** (créé automatiquement au premier lancement).
* Tables : `settings` (paramètres), `transactions`, `invoices`, `payments`,
  `users` (comptes et empreintes des codes).
* Toutes les requêtes sont **paramétrées** (`?`) : pas d'injection SQL possible.
* Les données restent disponibles après fermeture de l'application.
* Pour repartir de zéro : page « Rapports et paramètres » → « Effacer les données ».
* Le fichier est ignoré par Git (`.gitignore`) : aucune donnée réelle n'est versionnée.

---

## 6. Contenu du projet

```
app.py                  Point d'entrée Streamlit (connexion, navigation, contexte)
connexion.py            Écran de connexion et déconnexion
auth.py                 Hachage des codes (PBKDF2), validation des identifiants
finance.py              Moteur de calcul financier (fonctions pures, Decimal)
db.py                   Couche SQLite (schéma, CRUD, paiements atomiques, comptes)
io_utils.py             Import CSV/Excel, exports CSV/Excel/PDF, DataFrames
assistant.py            Assistant financier local (règles, français)
demo_data.py            Générateur du jeu de démonstration
theme.py                Habillage (CSS, cartes KPI, alertes, graphiques)
views/                  Une page de l'application par fichier
tests/                  Tests unitaires et tests d'intégration Streamlit
lancer.bat              Lancement automatique sous Windows
requirements.txt        Dépendances
```

---

## 7. Limites connues (honnêteté du prototype)

* **Assistant local par règles** : il reconnaît une trentaine d'intentions prédéfinies
  (mots-clés français, accents ignorés). Il ne comprend pas le langage naturel libre et le
  dit clairement plutôt que d'inventer un chiffre. L'architecture (`assistant.get_provider()`)
  est prête pour un futur fournisseur d'IA externe optionnel.
* **Prévisions déterministes** : aucune probabilité de paiement n'est modélisée, aucun
  modèle de machine learning n'est utilisé (les données disponibles ne permettraient pas
  de le valider). Les montants projetés sont des **estimations**.
* **Délai de recouvrement estimé** paramétrable (7 jours par défaut) : hypothèse simple,
  pas un modèle de comportement de paiement.
* **Devise** : MAD uniquement dans cette version (aucune conversion de devises).
* **Pas de multi-utilisateur simultané** : l'authentification est locale et sert à
  restreindre l'accès sur un poste donné. Il n'y a ni rôles serveur, ni récupération de
  code par e-mail, ni journal d'audit ; la base SQLite reste lisible par quiconque a
  accès au fichier.
* **PDF** : généré via `reportlab` (téléchargement depuis la page Rapports). Si la
  bibliothèque est absente, l'application le signale et les exports CSV/Excel restent
  disponibles.
* **Import** : seules les transactions sont importables (CSV/Excel) ; les factures se
  saisissent dans l'application.
* Un paiement identique (même facture, même date, même montant) est refusé : c'est une
  protection anti-doublon, mais deux versements réellement identiques le même jour
  doivent être saisis avec des montants légèrement différents ou une date différente.

---

## 8. Sécurité et fiabilité

* Requêtes SQL paramétrées, validations systématiques des montants/dates/statuts.
* Transactions SQLite (`with conn:`) pour les opérations facture + paiement + trésorerie.
* Suppression d'une transaction de règlement = annulation du paiement et recalcul du solde.
* Aucune clé d'API ni donnée personnelle dans le code ou le jeu de démonstration.
* `.gitignore` fourni (environnements virtuels, base locale, secrets, exports).

---

*Prototype académique — Fintech & IA appliquée. Aucune connexion bancaire réelle ;
toutes les données de démonstration sont fictives.*
