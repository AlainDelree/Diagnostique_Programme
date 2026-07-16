"""Classe `Profile` — socle commun des profils par technologie (§4.6).

Un profil est essentiellement de la *donnée* : quelles extensions comptent
comme source, quelles exclusions ajouter, quels motifs reconnaître pour
étiqueter une couche via convention (§4.5). Le moteur générique (§4) ne
change jamais quand on ajoute un profil.

Un profil concret fournit typiquement :
- `matches()` : signature de détection (fichiers/dossiers révélateurs) ;
- `layer_for()` : règle de couche par nom de fichier (convention §4.5) ;
- `classify()` : surchargé si l'étiquetage demande du contenu (ex. grep JDBC
  du profil Java/NetBeans) ;
- `conventions()` / `tech_identity()` : ce que le profil sait dire du projet.

Aucune méthode n'exécute quoi que ce soit sur le dépôt : lecture seule (§2).
"""

from __future__ import annotations

import os

from ..engine import DEFAULT_FUNC_DEF_PATTERNS, Heuristics
from ..exclusions import Exclusions
from ..model import FileInfo, Finding, Layer, TechIdentity


class Profile:
    """Profil générique par défaut. Les profils concrets en héritent."""

    name: str = "générique"
    language: str = "indéterminé"

    # `None` ⇒ on laisse le moteur utiliser ses extensions par défaut.
    source_extensions: frozenset[str] | None = None
    extra_excluded_dirs: frozenset[str] = frozenset()
    extra_globs: tuple[str, ...] = ()
    func_def_patterns: tuple[str, ...] = DEFAULT_FUNC_DEF_PATTERNS

    # -- détection (§4.5) ----------------------------------------------------

    def matches(self, repo_path: str) -> tuple[bool, str]:
        """Le profil reconnaît-il ce dépôt ? Renvoie (oui/non, raison lisible).

        Le générique ne « matche » jamais activement : il est le fallback,
        sélectionné explicitement en dernier par `detect_profile`.
        """
        return False, ""

    # -- construction du moteur ---------------------------------------------

    def make_exclusions(self) -> Exclusions:
        return Exclusions(self.extra_excluded_dirs, self.extra_globs)

    def make_heuristics(self, repo_path: str) -> Heuristics:
        """Moteur d'heuristiques (§4) paramétré par les *données* du profil."""
        return Heuristics(
            repo_path,
            source_extensions=self.source_extensions,
            exclusions=self.make_exclusions(),
            func_def_patterns=self.func_def_patterns,
        )

    # -- étiquetage des couches (§4.5) --------------------------------------

    def layer_for(self, relpath: str) -> tuple[Layer, str] | None:
        """Couche déduite du seul *nom* de fichier (convention §4.5), ou None.

        Surcharge simple pour les profils dont les conventions sont portées
        par le nommage (Django : `models.py` → Persistance). Renvoyer None
        laisse le fichier en `UNKNOWN` (repérable ensuite par taille/fan-in).
        """
        return None

    def classify(self, h: Heuristics, files: list[FileInfo]) -> None:
        """Étiquette chaque fichier avec sa couche quand une convention matche.

        Implémentation par défaut : applique `layer_for()`. Un profil dont
        l'étiquetage exige le contenu (ex. grep JDBC → Persistance) surcharge
        entièrement cette méthode.
        """
        for f in files:
            verdict = self.layer_for(f.path)
            if verdict is not None:
                f.layer, f.layer_reason = verdict

    # -- ce que le profil sait dire du projet -------------------------------

    def conventions(self, h: Heuristics, files: list[FileInfo]) -> list[str]:
        """Conventions reconnues, en clair (pour §5.2)."""
        return []

    def findings(self, h: Heuristics, files: list[FileInfo]) -> list[Finding]:
        """Points d'attention *spécifiques à la techno* (§5.4), ou aucun.

        Ex. le profil Java/NetBeans y signale les requêtes SQL construites par
        concaténation de chaînes. Jamais de suggestion de correctif (§5.4) :
        on nomme le point, pas la solution.
        """
        return []

    def tech_identity(self, h: Heuristics) -> TechIdentity:
        """Identité technique du projet (§5.2), au mieux de ce que sait le profil."""
        return TechIdentity(language=self.language, readme_excerpt=read_readme(h.repo))


# -- utilitaires partagés par les profils -----------------------------------

def read_readme(repo_path: str, max_chars: int = 800) -> str:
    """Début du README s'il existe (identité technique §5.2). Lecture seule."""
    for name in ("README.md", "README.rst", "README.txt", "README", "readme.md"):
        path = os.path.join(repo_path, name)
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read().strip()
            except OSError:
                return ""
            return text[:max_chars] + (" […]" if len(text) > max_chars else "")
    return ""


def exists(repo_path: str, *relparts: str) -> bool:
    """Un fichier/dossier existe-t-il dans le dépôt ? (signatures de détection)."""
    return os.path.exists(os.path.join(repo_path, *relparts))
