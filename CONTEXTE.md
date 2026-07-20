# Contexte — diagnostique_programme (outil d'audit Bridge_Agent)

## Objectif
Outil de **diagnostic/audit de projet** : permettre à Alain de reprendre
en main un dépôt laissé de côté (ou repris d'autrui) en obtenant vite son
architecture (persistance / métier / vue), ce qui marche ou non, et par où
continuer. Fonctionne dans l'esprit Bridge_Agent : CCL audite un dépôt via
des issues GitHub, en **lecture seule stricte** — l'outil ne modifie,
n'installe ni n'exécute jamais rien sur le dépôt audité. Voir
`SPEC_audit_projet.md` pour la spécification de référence (les modules
citent ses paragraphes, ex. « §4.3 »).

## Architecture
Paquet Python `audit/`, séparation nette **analyse → rendu** (un seul état
calculé, jamais recalculé au rendu) :
- `model.py` — modèle partagé : `AuditResult`, `FileInfo`, `Finding`,
  `Excerpt`, `TechIdentity`, enums `Layer` / `LayerState` / échelles verdict.
- `engine.py` — moteur générique d'heuristiques (taille, densité, fan-in
  par grep — approximatif, cf. `FAN_IN_CAVEAT`), indépendant de toute techno.
- `exclusions.py` — bruit à ignorer (généré/deps/build exclus ; tests/locale
  pondérés faible).
- `profiles/` — profils par techno (données, pas de logique moteur) :
  `base.Profile` (socle), `generic` (fallback UNKNOWN), `java_netbeans`
  (JDBC brut, paires `.java`/`.form` Swing, signature `nbproject/`/`build.xml`),
  `django` (couches par nom de fichier).
- `analysis.py` — le « Chef » : détecte le profil, lance le moteur, étiquette
  les couches, remplit `AuditResult`. L'état fonctionnel/cassé est laissé
  honnêtement « indéterminé » (pas d'exécution).
- `verdict.py` — verdict qualitatif *formateur* (constat + pourquoi, deux
  axes complexité×qualité, jamais de note chiffrée).
- `dynamic.py` — pistes de vérification dynamique : *propose* des commandes
  (compile/tests/run) sans les exécuter.
- `reports.py` — trois livrables : mémo humain, carte IA avec dépôt, carte IA
  + extraits. Un point d'attention = une ligne `chemin:ligne — [type] desc`,
  plafonné par catégorie, sans suggestion de correctif.
- `__main__.py` — point d'entrée CLI `python3 -m audit` (args `--repo`,
  `--profil`, `--sortie`, `--format`, `--version`) ; câblage pur, aucune
  logique dupliquée.

Périmètre non fixe : le dépôt cible est fourni par issue (`REPO_CIBLE`,
`PROFIL_TECHNO`), pas codé dans un `.conf`.

## Stack / dépendances
Python 3 pur, **bibliothèque standard uniquement** (dataclasses, enum, re,
os, argparse). Aucune dépendance tierce. `.tmp_fixture/Com/` = projet
Java/NetBeans factice servant de fixture de test au profil java_netbeans.

## Conventions de code observées
- Docstring de module riche en tête de chaque fichier, renvoyant aux § de la
  spec.
- `from __future__ import annotations` partout ; type hints.
- Commentaires et identifiants « métier » en **français**.
- Séparation stricte analyse/rendu ; profils = données, moteur générique
  jamais modifié pour ajouter un profil.
- Sauvegarde git `avant-<desc> --allow-empty` avant chaque tâche d'écriture.

## État d'avancement
Implémenté : modèle, moteur, exclusions, profils (generic, java_netbeans,
django), analyse, verdict, pistes dynamiques, rapports, CLI. En cours :
classement Métier par élimination du profil Java/NetBeans (issue #5).
Pas de fichier TODO/TACHES ; le suivi se fait par issues GitHub et par le
journal des commits.

## Maintenance de ce fichier
Si la tâche que tu exécutes modifie l'architecture, les dépendances, les
conventions de code, ou l'état d'avancement majeur de ce projet, mets à
jour ce CONTEXTE.md en conséquence, dans le même commit.
