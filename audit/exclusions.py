"""Exclusions génériques — le bruit à ignorer (§4.4).

Deux niveaux :
- exclusion *totale* : généré / dépendances / build — n'a rien à dire sur
  le projet lui-même (`node_modules/`, `target/`, `*.lock`, ...) ;
- pondération *réduite* : dense mais pas « métier » au même titre
  (`tests/`, `spec/`, `locale/`) — on les garde mais ils pèsent moins.

Un profil (§4.6) peut ajouter ses propres exclusions via `extra_dirs` /
`extra_globs` sans toucher à ce module.
"""

from __future__ import annotations

import fnmatch
import os

# Dossiers exclus totalement (généré, dépendances, build, VCS, IDE).
# `nbproject/` est volontairement absent : c'est une *signature* du profil
# Java/NetBeans (§4.6), on veut donc pouvoir le lire.
EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    "dist", "build", "out", "target",  # target/ = Maven/Java (§4.4)
    "vendor",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".venv", "venv", "env", ".env",
    ".idea", ".vscode", ".gradle",
    "coverage", "htmlcov",
    "migrations",  # §4.4 (Django & co.)
})

# Motifs de fichiers exclus totalement (lock, généré, compilé, minifié).
EXCLUDED_GLOBS: tuple[str, ...] = (
    "*.lock", "*-lock.json", "package-lock.json", "yarn.lock",
    "*.pyc", "*.pyo", "*.class", "*.o", "*.so", "*.dll",
    "*.min.js", "*.min.css",
    "*.map",
    "*.jar", "*.war",  # dépendances binaires (analysées à part, pas comptées)
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.svg", "*.pdf",
    "*.zip", "*.tar", "*.gz", "*.rar",
)

# Dossiers dé-pondérés (denses mais pas « métier ») → poids réduit (§4.4).
DOWNWEIGHTED_DIRS: frozenset[str] = frozenset({
    "tests", "test", "spec", "specs", "__tests__",
    "locale", "locales", "i18n", "lang",
    "fixtures", "testdata", "test_data", "samples",
    "docs", "doc",
})
DOWNWEIGHT_FACTOR = 0.3


class Exclusions:
    """Décide, pour un chemin, s'il est exclu et quel poids lui donner."""

    def __init__(
        self,
        extra_dirs: frozenset[str] | None = None,
        extra_globs: tuple[str, ...] = (),
    ) -> None:
        self.excluded_dirs = EXCLUDED_DIRS | (extra_dirs or frozenset())
        self.excluded_globs = EXCLUDED_GLOBS + tuple(extra_globs)

    def is_excluded_dir(self, dirname: str) -> bool:
        return dirname in self.excluded_dirs or dirname.startswith(".")

    def is_excluded_file(self, relpath: str) -> bool:
        parts = relpath.split(os.sep)
        if any(p in self.excluded_dirs for p in parts[:-1]):
            return True
        name = parts[-1]
        return any(fnmatch.fnmatch(name, g) for g in self.excluded_globs)

    def weight(self, relpath: str) -> float:
        """Poids d'un fichier (1.0 par défaut, réduit sous un dossier dé-pondéré)."""
        parts = relpath.split(os.sep)
        if any(p in DOWNWEIGHTED_DIRS for p in parts[:-1]):
            return DOWNWEIGHT_FACTOR
        return 1.0
