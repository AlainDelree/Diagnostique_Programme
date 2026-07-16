# Spec — Outil de diagnostic/audit de projet (Bridge_Agent)

> Statut : conception, pas encore implémenté. Document de référence pour la
> rédaction de l'issue Chef et l'adaptation du watcher.

---

## 1. Objectif

Permettre à Alain de reprendre en main un projet qu'il a laissé tomber
pendant plusieurs mois (ou repris de quelqu'un d'autre) en obtenant
rapidement :

- l'architecture du projet (persistance, métier, interface),
- ce qui fonctionne / ne fonctionne pas / est incomplet,
- comment continuer concrètement.

Fonctionne dans l'esprit Bridge_Agent : CCL analyse un dépôt via des
issues GitHub, en **lecture seule** dans un premier temps.

---

## 2. Intégration Bridge_Agent

Nouveau projet `audit`, avec une particularité par rapport aux projets
existants (§7 de la doc générale) : son périmètre n'est pas un dossier fixe
codé dans le `.conf`, mais fourni à chaque issue via un champ dédié.

**Champs d'en-tête spécifiques à ajouter :**

| Champ | Valeur | Effet |
|-------|--------|-------|
| `REPO_CIBLE` | chemin absolu | Dépôt à auditer pour cette issue (remplace le périmètre fixe du §7) |
| `PROFIL_TECHNO` | ex. `java-netbeans`, `django`, `auto` | Force ou laisse détecter automatiquement le profil technologique |

Mode par défaut : **lecture seule stricte** (pas de `mode_write`). CCL ne
modifie rien, n'installe rien, n'exécute rien — sauf lors de l'étape 2
optionnelle (§6).

---

## 3. Architecture du traitement — pattern Chef + Specs

Reprend le pattern §15 (Chef + Specs MVC) plutôt qu'un chef/ouvrier ad hoc
générique (§14), car le découpage est fixe et récurrent :

- **Ouvrier Persistance** : modèles de données, schéma DB, requêtes SQL,
  migrations, fichiers de config de connexion.
- **Ouvrier Métier** : logique applicative, contrôleurs, règles métier,
  fonctions centrales.
- **Ouvrier Vue** : templates, front, formulaires, routes/API.

Chaque ouvrier produit un rapport partiel. Le **Chef** assemble les trois
rapports, ajoute une vue transversale (cohérence entre couches, comment
elles communiquent) et génère les livrables finaux (§5).

---

## 4. Heuristiques de repérage (moteur générique, lecture seule)

Objectif : repérer les zones qui comptent sans analyse d'exécution.

### 4.1 Fichiers volumineux
`wc -l` sur les fichiers source, tri décroissant. Signal : un fichier a
souvent grossi au fil du temps sans être refactoré → probablement central
ou en dette technique.

### 4.2 Dossiers denses
Comptage de fichiers par dossier. Un dossier qui sort du lot signale une
zone déjà éclatée en petits fichiers (signe d'un refactor passé) →
probablement le cœur du métier.

### 4.3 Fonctions à fort "fan-in"
Grep du nom de fonction/méthode sur tout le repo, comptage des occurrences
hors définition. Approximation grossière (pas de résolution de scope réelle)
mais suffisante pour repérer les fonctions réellement centrales.
**À signaler dans le rapport comme "estimation par grep, approximative"**
pour ne pas donner un faux sentiment de précision.

### 4.4 Exclusions génériques (bruit à ignorer)
`migrations/`, `*.lock`, `node_modules/`, `dist/`, `vendor/`,
`target/` (Maven/Java), fixtures/données de test volumineuses, fichiers
générés/compilés. Pondération réduite (pas exclusion totale) pour
`tests/`, `spec/`, `locale/` — denses mais pas "métier" au même titre.

### 4.5 Profiter d'une structure déjà bien nommée
Avant d'appliquer les heuristiques brutes ci-dessus, confronter
l'arborescence à un **dictionnaire de conventions connues** par techno
(§4.6). Si ça matche, étiqueter directement ("Couche Persistance identifiée
via convention DAO") ; sinon, retomber sur taille/densité/fan-in.

### 4.6 Profils par technologie
Cœur généraliste + fichiers de config par techno (motifs de
dossiers/fichiers à reconnaître, exclusions spécifiques). Un profil est une
liste de motifs, pas du code — extensible sans toucher au moteur.

**Profil générique (fallback)** : heuristiques §4.1–4.4 seules.

**Profil Django/Python** (projets actifs) : `models.py`, `views.py`,
`urls.py`, `migrations/` reconnus comme conventions.

**Profil Java/NetBeans artisanal** (premier cas de test — projet ancien
sans Maven/Gradle) :
- Signature de détection : présence de `nbproject/`, `build.xml` (Ant).
- Vue : paires `NomClasse.java` + `NomClasse.form` (formulaires Swing
  générés par NetBeans) → cartographie fiable des écrans.
- Persistance : grep `DriverManager`, `Connection`, `Statement`,
  `ResultSet`, mots-clés SQL en littéral (JDBC brut, pas d'ORM) →
  cartographie des accès MySQL. Détecter aussi les requêtes construites
  par concaténation de chaînes (signalé en point d'attention, §5.4 —
  jamais de suggestion de correctif à ce stade).
- Dépendances : `nbproject/project.xml` (classpath) et/ou dossier `lib/`
  contenant des `.jar` nommés explicitement (ex. driver JDBC MySQL).
- Métier : par élimination, souvent dans des classes appelées depuis les
  gestionnaires d'événements des formulaires (`jButtonXActionPerformed`) —
  recoupe l'heuristique de fan-in (§4.3).

---

## 5. Livrables

Deux familles de rapport, chacune avec un usage différent.

### 5.1 Rapport humain
Mémo de reprise en main, pour Alain lui-même.

- Résumé exécutif en tête (3-4 lignes : état de santé global, effort
  estimé pour relancer) — sert accessoirement d'aide à la décision
  "reprendre ou archiver", sans être un objectif premier.
- État par couche (fonctionnel / cassé / incomplet).
- Dette technique repérée.
- Comment relancer concrètement (dépendances, commande, config nécessaire).
- Prochaines étapes suggérées, classées par priorité.

### 5.2 Rapport IA — variante "avec accès repo"
Pour relancer un CCL (ou toute IA outillée) qui pourra lire le code
elle-même. Une **carte**, pas un cours :
- Inventaire des fichiers par couche (une ligne de description chacun).
- Points d'entrée (fichier principal, commande de lancement).
- Conventions repérées.
- Pièges connus (`chemin:ligne` + description courte, format §5.4).
- TODO/incohérences à vérifier.
- Section "Identité technique du projet" (langage/version, framework(s),
  gestionnaire de dépendances, dépendances principales, contenu du README
  s'il existe).

Volontairement compact — l'IA destinataire ira lire le détail elle-même.

### 5.3 Rapport IA — variante "sans accès repo"
Pour discuter du projet dans un chat Claude ou une autre IA en ligne, sans
lui donner accès au code à ce moment-là. Même squelette que §5.2, enrichi
de :
- Extraits de code réels aux points d'architecture centraux (schéma de
  données principal, fonction métier pivot par couche).
- Extraits autour de chaque problème identifié — pas de couverture
  exhaustive, sinon explosion en taille sur un gros projet.

**Choix du format à générer** : case à cocher / option au moment de créer
l'issue (avec accès repo / sans accès repo / les deux).

### 5.4 Règle de concision (s'applique aux §5.2 et 5.3)
- Un point d'attention = une ligne, format fixe :
  `chemin:ligne — [type] description courte`
  (ex. `UserDAO.java:47 — [SQL fragile] requête construite par
  concaténation de chaînes`).
- Pas de justification longue, pas de suggestion de correctif — le
  correctif reste une décision d'Alain (avec l'IA si besoin), pas une
  initiative de l'audit.
- Plafond par catégorie de problème (ex. 10 occurrences les plus
  significatives, triées par l'heuristique de fan-in/taille), avec mention
  explicite type "10 sur 34 occurrences détectées" si le plafond est
  atteint.

---

## 6. Étape 2 (optionnelle, différée) — pistes de vérification dynamique

Puisqu'on reste en lecture seule stricte à l'étape 1, tout doute qui
nécessiterait une exécution réelle (le projet compile-t-il vraiment ? les
tests passent-ils ? le serveur démarre-t-il ?) est noté dans une section
dédiée du rapport IA : **"Pistes de vérification dynamique"** — une liste
de commandes concrètes (`pip install -r requirements.txt`, `pytest`,
`python manage.py runserver`, etc.), chacune reliée au doute qu'elle est
censée trancher.

Ces pistes ne sont **pas** exécutées automatiquement. Une issue de suivi
séparée (`SUITE_DE`) peut demander explicitement à CCL de les exécuter,
dans un environnement isolé (venv dédié), sans toucher au code source.

> Note pour plus tard : ceci suggère une nuance à trois niveaux
> (lecture seule / exécution sans modification / écriture) plutôt que le
> binaire actuel lecture-seule ↔ `mode_write`. À introduire seulement si
> le besoin se confirme en pratique.

La reprise en main réelle (coder sur le projet) reste un **troisième
temps distinct** : un CCL classique en `mode_write`, avec le rapport final
(humain + IA) fourni en `FICHIER_CONTEXTE` (§6 de la doc générale).

---

## 7. Cas de test retenu

Projet Java/MySQL ancien, artisanal (pas de Maven/Gradle), fait via
NetBeans, sans IA lors de son développement initial. Choisi comme premier
test car plus exigeant que les projets actifs (pas de conventions Django
toutes faites, pas de README à jour probable) — bon test de robustesse du
cœur généraliste avant application à des projets plus récents.

---

## 8. Verdict qualitatif formateur (architecture/conception)

Objectif différent d'un simple état des lieux : ce verdict sert à
**progresser**, pas juste à documenter. Il doit permettre de repérer ses
erreurs récurrentes et de conforter ce qui est déjà bien fait — sans
complaisance, mais sans sécheresse gratuite non plus.

### 8.1 Signaux objectifs utilisés (dérivés des heuristiques §4)

- **Séparation des responsabilités** : SQL/logique métier trouvés dans les
  fichiers étiquetés Vue ? Dépendance directe du Métier vers le framework
  de Vue ? (grep croisé entre couches identifiées au §4.6)
- **Concentration vs éclatement** : logique répartie en unités cohérentes,
  ou concentrée dans quelques fichiers volumineux qui font tout
  (dérivé de §4.1) ?
- **Présence de tests** : dossier de tests existant, substantiel ou
  squelette vide ?
- **Cohérence des conventions** : nommage homogène, ou mélange de styles
  trahissant plusieurs "époques" de développement ?
- **Duplication** : blocs quasi identiques repérables par grep sur motifs
  distinctifs (approximatif mais suffisant pour signaler une zone à
  factoriser).

### 8.2 Règle de rédaction : nommer l'erreur ET pourquoi c'est un problème

Ne jamais se contenter du constat brut. Chaque point, positif ou négatif,
doit être accompagné de sa justification — c'est cette explication qui
permet d'apprendre, pas le constat seul.

- Mauvais exemple (à éviter) : *"SQL en dur dans le contrôleur."*
- Bon exemple : *"SQL en dur dans le contrôleur — mélange Vue et
  Persistance, ce qui rend le code difficile à réutiliser ailleurs et
  fragile si la structure de la table change."*
- Symétriquement pour les points forts : *"Séparation Vue/Métier respectée
  dans le module X — permet de modifier l'affichage sans toucher à la
  logique, exactement le bénéfice recherché."*

Ton : factuel et pédagogique. Ni complaisance diplomatique, ni liste de
reproches secs.

### 8.3 Évaluation qualitative globale à deux axes

Plutôt qu'un jugement unique ("bon"/"mauvais projet"), distinguer deux
axes indépendants, parce que ce sont deux compétences différentes à
travailler :

- **Complexité conceptuelle** : le problème adressé par le projet était-il
  intrinsèquement simple ou ambitieux (nombre d'entités métier, règles
  métier imbriquées, cas particuliers gérés) ?
- **Qualité d'exécution** : indépendamment de l'ambition du projet,
  l'implémentation est-elle propre (signaux du §8.1) ?

Ces deux axes croisés donnent un positionnement utile — ex. *"Projet
compliqué conceptuellement mais techniquement impeccable"* ou à l'inverse
*"Projet simple mais implémentation confuse"*. Chaque combinaison appelle
un conseil différent pour le prochain projet, contrairement à un score
unique qui les confondrait.

**Pas de note chiffrée** — le positionnement sur les deux axes reste
qualitatif et toujours accompagné du raisonnement (§8.2), jamais un score
isolé qui masquerait le "pourquoi".

### 8.4 Portée v1 : audit isolé, mais format compatible avec une mémoire future

Pour cette v1, chaque audit reste indépendant (pas de comparaison
automatique avec les audits précédents). Cependant, pour ne pas devoir
tout refactorer plus tard si une mémoire de patterns récurrents
(`PATTERNS_CONNUS.md` ou équivalent, alimenté à chaque audit) est ajoutée :

- Les points du §8.2 doivent être formulés de façon **catégorisable**
  (ex. toujours préfixés par un type : `[SQL en dur]`, `[fichier
  monolithique]`, `[absence de tests]`...) plutôt qu'en prose libre —
  cohérent avec le format `chemin:ligne — [type] description` déjà retenu
  au §5.4.
- Le positionnement à deux axes (§8.3) doit rester sur une échelle stable
  et nommée (pas de vocabulaire réinventé à chaque audit), pour qu'une
  future comparaison entre audits successifs reste possible sans
  changer le format rétroactivement.

---

## 9. Points ouverts / à trancher en implémentation

- Adaptation du watcher pour accepter `REPO_CIBLE` en paramètre d'issue
  plutôt qu'un périmètre fixe par `.conf`.
- Mécanisme de sélection du format de rapport à générer (avec/sans accès
  repo / les deux) au moment de la création de l'issue.
- Format de sortie du rapport final : commentaire d'issue simple vs fichier
  commité dans le repo audité (ce second choix sortirait du lecture seule
  strict, nécessiterait un `mode_write` limité à la création de ce seul
  fichier).
- Introduction éventuelle du niveau intermédiaire "exécution sans
  modification" (§6), à valider après premier usage réel.

---

*Document de conception — à transformer en issue Chef Bridge_Agent une
fois les points ouverts du §9 tranchés.*
