"""Pistes de vérification dynamique (§6), dérivées d'un `AuditResult`.

L'audit reste en **lecture seule stricte** (§2). Certains doutes ne peuvent
pourtant *pas* être tranchés par la seule lecture : le projet compile-t-il
vraiment ? les dépendances déclarées s'installent-elles encore ? les tests
passent-ils ? l'application démarre-t-elle ? L'état « fonctionnel / cassé »
d'une couche est d'ailleurs laissé honnêtement « indéterminé » par l'analyse
(§5.1) faute d'exécution.

Ce module transforme ces doutes en une liste de **commandes suggérées**
(`DynamicCheck`), chacune reliée explicitement au doute qu'elle trancherait.
Rien n'est exécuté ici : conformément au §6, ces pistes sont uniquement
*proposées*. Une issue de suivi séparée (`SUITE_DE`) peut demander à CCL de
les lancer, dans un environnement isolé (venv dédié), sans toucher au code.

Les commandes ne sont pas devinées : elles sont dérivées de l'identité
technique déjà remplie par le profil (§5.2) — `dependency_manager`,
`frameworks`, `run_command` — et de la présence (ou non) d'un dossier de
tests. Un profil qui ne sait rien dire ne produit aucune piste (liste vide),
plutôt que des commandes inventées.
"""

from __future__ import annotations

import os

from .model import (
    AuditResult,
    DynamicCheck,
    FileInfo,
    Layer,
)

# Segments de chemin trahissant un dossier de tests (aligné sur §4.4 / §8.1).
_TEST_SEGMENTS = frozenset({"test", "tests", "spec", "specs", "__tests__"})


def build_dynamic_checks(result: AuditResult) -> list[DynamicCheck]:
    """Construit les pistes de vérification dynamique (§6).

    Ordre volontaire — celui dans lequel on lèverait réellement les doutes :
    installer les dépendances, compiler/charger, lancer les tests, démarrer
    l'application. Chaque piste ne sort que si l'analyse a de quoi la formuler
    sans inventer de commande.
    """
    checks: list[DynamicCheck] = []
    for builder in (_install_check, _build_check, _tests_check, _run_check):
        check = builder(result)
        if check is not None:
            checks.append(check)
    return checks


# --- doute : les dépendances déclarées s'installent-elles ? -----------------

def _install_check(result: AuditResult) -> DynamicCheck | None:
    """Installation des dépendances — un `import`/lien manquant ne se voit pas
    à la lecture (versions retirées de l'index, conflits, dépendance système)."""
    dm = result.tech.dependency_manager or ""
    if "requirements.txt" in dm:
        command = "pip install -r requirements.txt"
    elif "pyproject.toml" in dm or "setup.py" in dm:
        command = "pip install -e ."
    elif "Pipfile" in dm:
        command = "pipenv install"
    else:
        # Java/Ant : pas d'étape d'installation (les .jar sont dans le
        # classpath) ; le doute se lève à la compilation → _build_check.
        return None
    return DynamicCheck(
        command=command,
        doubt=(
            "les dépendances déclarées s'installent-elles encore proprement "
            "(versions toujours disponibles, aucun conflit) ? Impossible à "
            "trancher par lecture seule."
        ),
        layer=Layer.UNKNOWN,
    )


# --- doute : le projet compile / se charge-t-il vraiment ? ------------------

def _build_check(result: AuditResult) -> DynamicCheck | None:
    """Compilation (Java) ou chargement de la config (Django) : un code qui se
    lit sans erreur peut malgré tout ne pas compiler / ne pas s'initialiser."""
    tech = result.tech
    if tech.language == "Java":
        return DynamicCheck(
            command="ant compile",
            doubt=(
                "le projet compile-t-il réellement (tous les .jar du classpath "
                "présents, code cohérent) ? La lecture statique ne le garantit pas."
            ),
            layer=Layer.UNKNOWN,
        )
    if "Django" in tech.frameworks:
        return DynamicCheck(
            command="python manage.py check",
            doubt=(
                "la configuration Django se charge-t-elle sans erreur (settings, "
                "apps, imports) ? Indécidable sans la faire s'initialiser."
            ),
            layer=Layer.UNKNOWN,
        )
    return None


# --- doute : les tests passent-ils ? ----------------------------------------

def _has_tests(files: list[FileInfo]) -> bool:
    return any(
        seg in _TEST_SEGMENTS
        for f in files
        for seg in f.path.split(os.sep)
    )


def _tests_check(result: AuditResult) -> DynamicCheck | None:
    """Exécution des tests — leur seule présence (§8.1) ne dit pas s'ils passent,
    échouent, ou sont devenus obsolètes. On ne propose la commande que si un
    dossier de tests existe et que la techno donne une commande fiable."""
    if not _has_tests(result.files):
        return None
    tech = result.tech
    if "Django" in tech.frameworks:
        command = "python manage.py test"
    elif tech.language == "Python":
        command = "pytest"
    elif tech.language == "Java":
        command = "ant test"
    else:
        return None
    return DynamicCheck(
        command=command,
        doubt=(
            "les tests existants passent-ils, ou révèlent-ils des régressions / "
            "du code devenu obsolète ? La présence d'un dossier de tests ne le dit pas."
        ),
        layer=Layer.UNKNOWN,
    )


# --- doute : l'application démarre-t-elle ? ---------------------------------

def _run_check(result: AuditResult) -> DynamicCheck | None:
    """Démarrage de l'application — c'est le seul moyen de trancher l'état
    « fonctionnel / cassé » que l'analyse a laissé « indéterminé » (§5.1)."""
    raw = result.tech.run_command
    if not raw:
        return None
    # `run_command` peut porter une parenthèse explicative (ex. « ant run  (ou
    # exécuter la classe main() depuis NetBeans) ») : on garde la commande nue.
    command = raw.split("(")[0].strip()
    if not command:
        return None
    return DynamicCheck(
        command=command,
        doubt=(
            "l'application démarre-t-elle sans erreur ? C'est la seule façon de "
            "trancher l'état « fonctionnel / cassé » des couches, laissé "
            "« indéterminé » par l'analyse statique (§5.1)."
        ),
        layer=Layer.VIEW,
    )
