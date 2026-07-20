"""Verdict qualitatif formateur (§8), calculé sur un `AuditResult`.

Objectif différent d'un simple état des lieux (§5) : ce verdict sert à
**progresser**, pas juste à documenter. Il repère les erreurs récurrentes et
conforte ce qui est déjà bien fait — sans complaisance ni sécheresse gratuite.

Découpage suivant la spec :
- §8.1 : signaux objectifs dérivés des heuristiques §4 (séparation des
  responsabilités, concentration vs éclatement, présence de tests, cohérence
  des conventions, duplication) ;
- §8.2 : chaque point (positif ou négatif) nomme le constat ET pourquoi c'est
  un problème/bénéfice — c'est l'explication qui fait apprendre, pas le constat
  seul. Porté par `VerdictPoint(observation, why)` ;
- §8.3 : deux axes indépendants, complexité conceptuelle × qualité d'exécution,
  positionnement qualitatif toujours accompagné du raisonnement — jamais de
  note chiffrée ;
- §8.4 : format catégorisable (chaque point préfixé d'un `[type]` stable) et
  échelles nommées/stables (`ConceptualComplexity`, `ExecutionQuality`) pour
  rester compatible avec une future mémoire de patterns (`PATTERNS_CONNUS.md`)
  — cette mémoire n'est **pas** implémentée ici, seul le format est gardé
  compatible.

Aucune exécution, aucune lecture disque supplémentaire : tout est dérivé de
l'`AuditResult` déjà calculé et du contenu déjà mis en cache par le moteur (§4).
"""

from __future__ import annotations

import os
import re
from collections import Counter

from .engine import Heuristics
from .model import (
    AuditResult,
    ConceptualComplexity,
    ExecutionQuality,
    FileInfo,
    Layer,
    Verdict,
    VerdictPoint,
)

# Dossiers dont les segments trahissent des tests (repérage de la présence de
# tests, §8.1). Aligné sur les dossiers dé-pondérés du moteur (§4.4).
_TEST_SEGMENTS = frozenset({"test", "tests", "spec", "specs", "__tests__"})

# En-dessous, on considère qu'un dossier de tests n'est qu'un squelette (§8.1).
_SUBSTANTIAL_TEST_LOC = 80

# SQL en clair (croisement inter-couches §8.1 : du SQL dans un fichier de Vue
# trahit un mélange Persistance/Vue). Approximatif, suffisant comme signal.
_SQL_IN_VIEW = re.compile(
    r'\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b.*\b(FROM|INTO|WHERE|SET|VALUES)\b',
    re.IGNORECASE,
)

# Une ligne « significative » pour la détection de duplication : ni trop courte
# (accolades, mots-clés isolés), ni commentaire. Approximatif (§8.1).
_DUP_MIN_LEN = 25
_DUP_COMMENT_PREFIXES = ("//", "#", "*", "/*", "<!--", "--", '"""', "'''")
# Une même ligne significative répétée au moins ce nombre de fois = copie/colle.
_DUP_OCCURRENCES = 4


def build_verdict(result: AuditResult, h: Heuristics) -> Verdict:
    """Construit le verdict formateur (§8) à partir des signaux objectifs.

    `result` porte déjà les couches, findings et fan-in (§4–5) ; `h` sert
    uniquement à relire le contenu *déjà en cache* pour les signaux qui exigent
    le texte (SQL croisé, duplication). Aucune lecture disque supplémentaire.
    """
    files = result.files
    points: list[VerdictPoint] = []

    # -- §8.1 signaux objectifs → §8.2 points « constat + pourquoi » ----------
    sep = _signal_separation(result, h)
    if sep is not None:
        points.append(sep)

    conc = _signal_concentration(result)
    if conc is not None:
        points.append(conc)

    tests = _signal_tests(files)
    if tests is not None:
        points.append(tests)

    conv = _signal_conventions(files)
    if conv is not None:
        points.append(conv)

    # Duplication : sur le seul code du projet — un copier-collé *interne* à une
    # bibliothèque tierce embarquée (vendored) n'est pas la dette du projet (§4.6).
    dup = _signal_duplication([f for f in files if not f.vendored], h)
    if dup is not None:
        points.append(dup)

    # -- §8.3 axes indépendants, dérivés des mêmes signaux -------------------
    weaknesses = [p for p in points if not p.positive]
    complexity, complexity_reason = _assess_complexity(result, h)
    execution, execution_reason = _assess_execution(files, weaknesses)

    return Verdict(
        complexity=complexity,
        execution=execution,
        complexity_reason=complexity_reason,
        execution_reason=execution_reason,
        points=points,
    )


# --- §8.1 signaux objectifs -------------------------------------------------

def _signal_separation(result: AuditResult, h: Heuristics) -> VerdictPoint | None:
    """Séparation des responsabilités : SQL/logique dans les fichiers de Vue ?

    Grep croisé (§8.1) : on cherche du SQL en clair dans les fichiers étiquetés
    Vue (§4.6). En trouver trahit un mélange Vue/Persistance.
    """
    view_paths = {f.path for f in result.files if f.layer == Layer.VIEW}
    has_persistence = any(f.layer == Layer.PERSISTENCE for f in result.files)
    if not view_paths:
        # Sans couche Vue identifiée, on ne peut pas juger ce croisement.
        return None

    offenders: list[str] = []
    for path, line, _txt in h.grep(_SQL_IN_VIEW.pattern, re.IGNORECASE):
        if path in view_paths:
            offenders.append(f"{path}:{line}")
    # Le profil peut déjà avoir remonté du « SQL fragile » côté Vue (§5.4).
    offenders += [
        f"{f.path}:{f.line}"
        for f in result.findings
        if f.kind == "SQL fragile" and f.layer == Layer.VIEW and f.line
    ]
    offenders = sorted(set(offenders))

    if offenders:
        head = ", ".join(offenders[:3])
        suffix = f" (+{len(offenders) - 3} autres)" if len(offenders) > 3 else ""
        return VerdictPoint(
            kind="séparation des responsabilités",
            positive=False,
            observation=f"accès SQL trouvé dans des fichiers de Vue ({head}{suffix})",
            why=(
                "mélange Vue et Persistance : l'affichage et le stockage sont "
                "couplés, ce qui rend le code difficile à réutiliser ailleurs et "
                "fragile dès que la structure des tables change"
            ),
        )
    if has_persistence:
        return VerdictPoint(
            kind="séparation des responsabilités",
            positive=True,
            observation="aucun accès SQL détecté dans les fichiers de Vue",
            why=(
                "Vue et Persistance restent séparées : on peut modifier "
                "l'affichage sans toucher aux accès données, exactement le "
                "bénéfice recherché"
            ),
        )
    return None


def _signal_concentration(result: AuditResult) -> VerdictPoint | None:
    """Concentration vs éclatement (dérivé de §4.1) : logique diluée dans quelques
    gros fichiers, ou répartie en unités cohérentes ?"""
    total_loc = sum(f.loc for f in result.files)
    if total_loc == 0:
        return None
    monoliths = [f for f in result.findings if f.kind == "fichier monolithique"]
    biggest = max(result.files, key=lambda f: f.loc, default=None)
    share = (biggest.loc / total_loc) if biggest else 0.0

    # Un seul fichier concentre une grosse part du code, ou plusieurs monolithes.
    if len(monoliths) >= 3 or share >= 0.30:
        if len(monoliths) >= 3:
            obs = (
                f"{len(monoliths)} fichiers monolithiques concentrent la logique "
                f"(le plus gros : `{biggest.path}`, {biggest.loc} lignes)"
            )
        else:
            obs = (
                f"un seul fichier (`{biggest.path}`) porte {share:.0%} des lignes "
                "du projet"
            )
        return VerdictPoint(
            kind="fichier monolithique",
            positive=False,
            observation=obs,
            why=(
                "une logique concentrée dans quelques fichiers qui « font tout » "
                "est plus dure à lire, à tester isolément et à faire évoluer sans "
                "tout casser — c'est une dette technique typique"
            ),
        )
    if not monoliths and len(result.files) >= 6:
        return VerdictPoint(
            kind="concentration",
            positive=True,
            observation="logique répartie en fichiers de taille raisonnable "
            "(aucun monolithe repéré)",
            why=(
                "des unités cohérentes et bornées se lisent et se testent une par "
                "une : c'est ce qui rend un projet reprenable sans tout relire"
            ),
        )
    return None


def _signal_tests(files: list[FileInfo]) -> VerdictPoint | None:
    """Présence de tests (§8.1) : dossier substantiel, squelette vide, ou absent ?"""
    test_loc = sum(
        f.loc
        for f in files
        if any(seg in _TEST_SEGMENTS for seg in f.path.split(os.sep))
    )
    if test_loc == 0:
        return VerdictPoint(
            kind="absence de tests",
            positive=False,
            observation="aucun dossier de tests repéré",
            why=(
                "sans filet de tests, toute reprise ou refonte se fait à l'aveugle : "
                "on ne sait pas ce qu'on casse, ce qui ralentit et fragilise chaque "
                "modification"
            ),
        )
    if test_loc < _SUBSTANTIAL_TEST_LOC:
        return VerdictPoint(
            kind="tests squelettiques",
            positive=False,
            observation=f"un dossier de tests existe mais reste maigre (~{test_loc} lignes)",
            why=(
                "un squelette de tests presque vide donne une fausse impression de "
                "sécurité : il faut l'étoffer pour qu'il protège réellement les "
                "parcours critiques"
            ),
        )
    return VerdictPoint(
        kind="présence de tests",
        positive=True,
        observation=f"dossier de tests substantiel (~{test_loc} lignes)",
        why=(
            "un filet de tests fourni permet de refactorer et faire évoluer le "
            "projet en confiance — un point fort à conserver"
        ),
    )


def _signal_conventions(files: list[FileInfo]) -> VerdictPoint | None:
    """Cohérence des conventions (§8.1) : nommage homogène, ou mélange de styles
    trahissant plusieurs « époques » de développement ?

    Approximatif : on compare, *dans la même extension dominante* (pour éviter
    de confondre les conventions de deux langages), la part de noms en snake_case
    et en camelCase/PascalCase.
    """
    by_ext: Counter[str] = Counter(f.ext for f in files)
    if not by_ext:
        return None
    dominant, _ = by_ext.most_common(1)[0]
    stems = [
        os.path.splitext(os.path.basename(f.path))[0]
        for f in files
        if f.ext == dominant
    ]
    snake = sum(1 for s in stems if "_" in s and s == s.lower() and re.search(r"[a-z]", s))
    camel = sum(1 for s in stems if re.search(r"[a-z][A-Z]", s) or re.match(r"[A-Z][a-z].*[A-Z]", s))
    total = snake + camel
    # Trop peu d'indices pour trancher : on ne dit rien plutôt que d'inventer.
    if total < 5:
        return None
    minority = min(snake, camel)
    if minority >= max(1, total // 4):  # les deux styles cohabitent nettement
        return VerdictPoint(
            kind="conventions hétérogènes",
            positive=False,
            observation=(
                f"nommage mixte sur les fichiers `{dominant}` "
                f"({snake} en snake_case, {camel} en camelCase — approximatif)"
            ),
            why=(
                "un mélange de styles de nommage trahit souvent plusieurs époques "
                "de développement et augmente la charge mentale du lecteur, qui "
                "doit deviner la convention à chaque fichier"
            ),
        )
    return VerdictPoint(
        kind="conventions cohérentes",
        positive=True,
        observation=f"nommage homogène sur les fichiers `{dominant}`",
        why=(
            "un style de nommage uniforme rend le code prévisible : on sait où "
            "chercher et comment nommer la suite sans hésiter"
        ),
    )


def _signal_duplication(files: list[FileInfo], h: Heuristics) -> VerdictPoint | None:
    """Duplication (§8.1) : blocs quasi identiques repérables par grep sur motifs
    distinctifs — approximatif mais suffisant pour signaler une zone à factoriser.

    Heuristique : une même ligne « significative » (ni triviale ni commentaire)
    répétée dans plusieurs fichiers est un indice de copier-coller.
    """
    counts: Counter[str] = Counter()
    for f in files:
        seen_in_file: set[str] = set()
        for line in h._read_lines(os.path.join(h.repo, f.path)):
            s = line.strip()
            if len(s) < _DUP_MIN_LEN or s.startswith(_DUP_COMMENT_PREFIXES):
                continue
            # On ne compte une ligne qu'une fois par fichier : ce qui nous
            # intéresse, c'est la répétition *inter*-fichiers (copier-coller).
            if s in seen_in_file:
                continue
            seen_in_file.add(s)
            counts[s] += 1
    hotspots = [s for s, c in counts.items() if c >= _DUP_OCCURRENCES]
    if len(hotspots) >= 8:
        return VerdictPoint(
            kind="duplication",
            positive=False,
            observation=(
                f"{len(hotspots)} lignes distinctives répétées à l'identique dans "
                f"≥{_DUP_OCCURRENCES} fichiers (estimation par grep, approximative)"
            ),
            why=(
                "du code copié-collé doit être corrigé à plusieurs endroits à "
                "chaque évolution : c'est une source classique de bugs oubliés et "
                "une zone à factoriser en priorité"
            ),
        )
    return None


# --- §8.3 évaluation à deux axes -------------------------------------------

def _assess_complexity(
    result: AuditResult, h: Heuristics
) -> tuple[ConceptualComplexity, str]:
    """Complexité *conceptuelle* (§8.3) : le problème adressé était-il simple ou
    ambitieux ? Approché par le nombre de couches réellement peuplées, le volume
    de fichiers et le nombre de symboles définis (proxy d'entités/comportements).

    C'est un axe *indépendant* de la qualité d'exécution : un projet ambitieux
    peut être mal fait, un projet simple très propre.
    """
    n_files = len(result.files)
    layers_present = sum(
        1
        for layer in (Layer.PERSISTENCE, Layer.BUSINESS, Layer.VIEW)
        if any(f.layer == layer for f in result.files)
    )
    n_symbols = len(h._candidate_symbols())
    detail = (
        f"{n_files} fichier(s), {layers_present}/3 couche(s) peuplée(s), "
        f"~{n_symbols} fonction(s)/méthode(s) définie(s)"
    )

    if layers_present >= 3 and (n_files >= 30 or n_symbols >= 60):
        level = ConceptualComplexity.AMBITIEUSE
        why = (
            "plusieurs couches et un nombre élevé d'entités/comportements : le "
            "projet s'attaque à un problème riche"
        )
    elif n_files <= 8 and n_symbols <= 15 and layers_present <= 1:
        level = ConceptualComplexity.SIMPLE
        why = (
            "peu de fichiers et d'entités, une seule couche dominante : le "
            "périmètre fonctionnel reste modeste"
        )
    else:
        level = ConceptualComplexity.MODEREE
        why = (
            "quelques couches et un nombre intermédiaire d'entités : ambition "
            "raisonnable, sans être triviale"
        )
    return level, f"{why} ({detail})."


def _assess_execution(
    files: list[FileInfo], weaknesses: list[VerdictPoint]
) -> tuple[ExecutionQuality, str]:
    """Qualité d'*exécution* (§8.3) : indépendamment de l'ambition, l'implémentation
    est-elle propre ? Dérivée du nombre de signaux faibles du §8.1 remontés.

    Pas de note chiffrée exposée (§8.3) : le compte de défauts ne sert qu'à
    choisir un niveau sur l'échelle nommée et stable (§8.4), toujours justifié.
    """
    n = len(weaknesses)
    has_tests = any(
        any(seg in _TEST_SEGMENTS for seg in f.path.split(os.sep)) for f in files
    )
    labels = ", ".join(f"[{w.kind}]" for w in weaknesses) if weaknesses else "aucun"

    if n == 0 and has_tests:
        level = ExecutionQuality.IMPECCABLE
        why = "aucun signal de fragilité remonté et un filet de tests présent"
    elif n <= 1:
        level = ExecutionQuality.SOLIDE
        why = "au plus un signal de fragilité — implémentation globalement saine"
    elif n == 2:
        level = ExecutionQuality.PERFECTIBLE
        why = "deux signaux de fragilité cumulés : des points concrets à retravailler"
    else:
        level = ExecutionQuality.FRAGILE
        why = (
            f"{n} signaux de fragilité cumulés : l'implémentation demande un "
            "effort d'assainissement avant toute évolution sereine"
        )
    return level, f"{why} (signaux faibles : {labels})."
