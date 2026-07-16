"""Point d'entrée CLI de l'outil d'audit — `python3 -m audit` (§ issue #4).

Fine couche d'orchestration : lit les arguments, appelle `run_audit()`
(analysis.py) puis les fonctions de rendu de `reports.py`. Aucune logique
d'analyse ni de rendu n'est dupliquée ici — ce module ne fait que *câbler*
la ligne de commande sur l'API Python existante.

Lecture seule sur le dépôt audité (§2) : le seul effet de bord possible est
l'écriture des rapports dans le dossier `--sortie` s'il est fourni.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .analysis import run_audit
from .reports import (
    ai_report_with_repo,
    ai_report_without_repo,
    human_report,
)

# Noms de profils exposés en ligne de commande → noms internes attendus par
# `run_audit(forced_profile=...)`. Les internes portent accents/tirets
# (`générique`, `java-netbeans`) peu commodes à taper : on offre des alias
# ASCII stables côté CLI et on traduit ici (point d'interprétation, issue #4).
_PROFILE_ALIASES = {
    "auto": "auto",
    "generic": "générique",
    "django": "django",
    "java_netbeans": "java-netbeans",
}

# Formats de rapport exposés → (titre lisible, fonction de rendu, suffixe de
# fichier). `tous` génère les trois. Un seul point de vérité pour l'ordre et
# les noms de fichiers.
_RENDERERS = {
    "humain": ("Rapport humain (§5.1)", human_report, "humain"),
    "ia-avec-repo": ("Rapport IA avec accès repo (§5.2)", ai_report_with_repo, "ia-avec-repo"),
    "ia-sans-repo": ("Rapport IA sans accès repo (§5.3)", ai_report_without_repo, "ia-sans-repo"),
}
_FORMAT_CHOICES = (*_RENDERERS, "tous")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m audit",
        description="Audite un dépôt en lecture seule et génère les rapports "
        "(humain + IA) prévus par SPEC_audit_projet.md.",
    )
    parser.add_argument(
        "--repo",
        required=True,
        metavar="CHEMIN",
        help="Dépôt à auditer (obligatoire). Lecture seule.",
    )
    parser.add_argument(
        "--profil",
        default="auto",
        choices=list(_PROFILE_ALIASES),
        help="Force un profil au lieu de la détection automatique "
        "(défaut : auto).",
    )
    parser.add_argument(
        "--sortie",
        metavar="DOSSIER",
        help="Dossier où écrire les rapports. Sans cette option, les rapports "
        "sont affichés sur la sortie standard.",
    )
    parser.add_argument(
        "--format",
        default="tous",
        choices=_FORMAT_CHOICES,
        help="Quel(s) rapport(s) générer (défaut : tous).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"outil d'audit {__version__}",
    )
    return parser


def _selected_formats(fmt: str) -> list[str]:
    """Liste des clés de `_RENDERERS` à produire pour le format demandé."""
    if fmt == "tous":
        return list(_RENDERERS)
    return [fmt]


def _emit(result, formats: list[str], sortie: str | None) -> list[str]:
    """Rend les rapports demandés ; écrit sur disque si `sortie`, sinon stdout.

    Renvoie la liste des chemins écrits (vide en mode stdout).
    """
    written: list[str] = []
    if sortie:
        os.makedirs(sortie, exist_ok=True)

    for i, key in enumerate(formats):
        title, render, suffix = _RENDERERS[key]
        text = render(result)
        if sortie:
            path = os.path.join(sortie, f"rapport-{suffix}.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            written.append(path)
        else:
            # Séparateur lisible entre rapports quand on en cumule plusieurs.
            if i:
                print("\n" + "=" * 78 + "\n")
            print(text, end="")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    repo = args.repo
    if not os.path.exists(repo):
        print(f"Erreur : le chemin --repo n'existe pas : {repo!r}", file=sys.stderr)
        return 2
    if not os.path.isdir(repo):
        print(f"Erreur : --repo doit être un dossier, pas un fichier : {repo!r}",
              file=sys.stderr)
        return 2

    forced = _PROFILE_ALIASES[args.profil]

    try:
        result = run_audit(repo, forced_profile=forced)
    except ValueError as exc:
        # Profil inconnu remonté par detect_profile — message clair, pas de trace.
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2

    formats = _selected_formats(args.format)
    written = _emit(result, formats, args.sortie)

    if written:
        print(f"Profil retenu : {result.profile_name} "
              f"({result.profile_detection_reason}).", file=sys.stderr)
        print("Rapport(s) écrit(s) :", file=sys.stderr)
        for path in written:
            print(f"  - {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
