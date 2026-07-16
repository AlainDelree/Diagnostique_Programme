"""Moteur générique d'heuristiques (§4.1–4.4), lecture seule.

But : repérer les zones qui comptent *sans* analyse d'exécution. Aucune de
ces heuristiques ne prétend à l'exactitude — le fan-in (§4.3) en particulier
est une estimation grossière par grep, à signaler comme telle dans le
rapport (l'attribut `FAN_IN_CAVEAT` porte l'avertissement).

Le moteur est indépendant de toute techno ; il reçoit un `Profile` (§4.6)
qui lui fournit uniquement des *données* : extensions source, exclusions
supplémentaires, motifs de définition de fonction pour le fan-in.
"""

from __future__ import annotations

import os
import re
from collections import Counter

from .exclusions import Exclusions
from .model import FileInfo

FAN_IN_CAVEAT = "estimation par grep, approximative (pas de résolution de scope)"

# Extensions considérées « source » par défaut (profil générique). Un profil
# peut restreindre cet ensemble.
DEFAULT_SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".java", ".kt", ".scala", ".groovy",
    ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
    ".rb", ".php", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".sql", ".sh", ".pl",
    ".html", ".css", ".scss",
    ".xml", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
})

# Motifs génériques de définition de fonction/méthode, pour extraire les
# symboles candidats au fan-in. Volontairement large ; un profil peut fournir
# les siens (plus précis) via `func_def_patterns`.
DEFAULT_FUNC_DEF_PATTERNS: tuple[str, ...] = (
    r"^\s*def\s+([A-Za-z_]\w+)\s*\(",  # Python
    r"^\s*(?:public|private|protected|static|final|\s)+[\w<>\[\]]+\s+([A-Za-z_]\w+)\s*\([^;]*\)\s*\{",  # Java-like
    r"^\s*function\s+([A-Za-z_]\w+)\s*\(",  # JS
)


class Heuristics:
    """Applique les heuristiques §4.1–4.4 à un dépôt et renvoie des FileInfo."""

    def __init__(
        self,
        repo_path: str,
        source_extensions: frozenset[str] | None = None,
        exclusions: Exclusions | None = None,
        func_def_patterns: tuple[str, ...] = DEFAULT_FUNC_DEF_PATTERNS,
    ) -> None:
        self.repo = os.path.abspath(repo_path)
        self.source_extensions = source_extensions or DEFAULT_SOURCE_EXTENSIONS
        self.exclusions = exclusions or Exclusions()
        self.func_def_patterns = [re.compile(p) for p in func_def_patterns]
        self._files: list[FileInfo] | None = None

    # -- collecte ------------------------------------------------------------

    def _read_lines(self, abspath: str) -> list[str]:
        try:
            with open(abspath, encoding="utf-8", errors="replace") as fh:
                return fh.read().splitlines()
        except OSError:
            return []

    def source_files(self) -> list[FileInfo]:
        """Parcours du dépôt, filtré par extensions + exclusions (§4.4)."""
        if self._files is not None:
            return self._files

        files: list[FileInfo] = []
        for root, dirs, names in os.walk(self.repo):
            # Élague les dossiers exclus *avant* de descendre (évite node_modules & co.).
            dirs[:] = [d for d in dirs if not self.exclusions.is_excluded_dir(d)]
            for name in names:
                ext = os.path.splitext(name)[1].lower()
                if ext not in self.source_extensions:
                    continue
                abspath = os.path.join(root, name)
                relpath = os.path.relpath(abspath, self.repo)
                if self.exclusions.is_excluded_file(relpath):
                    continue
                loc = len(self._read_lines(abspath))
                files.append(FileInfo(
                    path=relpath,
                    loc=loc,
                    ext=ext,
                    weight=self.exclusions.weight(relpath),
                ))
        self._files = files
        return files

    # -- §4.1 fichiers volumineux -------------------------------------------

    def large_files(self, top: int = 15) -> list[FileInfo]:
        """Fichiers source triés par LOC décroissant (pondéré pour le tri)."""
        files = self.source_files()
        return sorted(files, key=lambda f: f.loc * f.weight, reverse=True)[:top]

    # -- §4.2 dossiers denses -----------------------------------------------

    def dense_dirs(self, top: int = 15) -> list[tuple[str, int]]:
        """Nombre de fichiers source par dossier, trié décroissant."""
        counts: Counter[str] = Counter()
        for f in self.source_files():
            d = os.path.dirname(f.path) or "."
            counts[d] += 1
        return counts.most_common(top)

    # -- §4.3 fan-in (approximatif) -----------------------------------------

    def _candidate_symbols(self) -> dict[str, tuple[str, int]]:
        """Symboles définis (nom -> (fichier, ligne de définition)).

        Sert de base au fan-in : on ne compte que des noms réellement définis
        quelque part, pas n'importe quel identifiant.
        """
        symbols: dict[str, tuple[str, int]] = {}
        for f in self.source_files():
            lines = self._read_lines(os.path.join(self.repo, f.path))
            for i, line in enumerate(lines, start=1):
                for pat in self.func_def_patterns:
                    m = pat.search(line)
                    if m:
                        name = m.group(1)
                        # Ignore constructeurs/accesseurs triviaux et noms trop courts.
                        if len(name) >= 3 and name not in symbols:
                            symbols[name] = (f.path, i)
        return symbols

    def fan_in(self, top: int = 15) -> list[tuple[str, int]]:
        """Occurrences de chaque symbole hors sa définition (approximation §4.3).

        Grep interne : on lit chaque fichier une fois et on compte les
        occurrences de chaque symbole (mot entier). Grossier — pas de
        résolution de scope — mais suffisant pour repérer le central.
        """
        symbols = self._candidate_symbols()
        if not symbols:
            return []
        patterns = {name: re.compile(rf"\b{re.escape(name)}\b") for name in symbols}
        counts: Counter[str] = Counter()
        for f in self.source_files():
            text = "\n".join(self._read_lines(os.path.join(self.repo, f.path)))
            for name, pat in patterns.items():
                n = len(pat.findall(text))
                if n:
                    counts[name] += n
        # On retire 1 occurrence par symbole : la définition elle-même.
        for name in list(counts):
            counts[name] -= 1
            if counts[name] <= 0:
                del counts[name]
        return counts.most_common(top)

    # -- grep utilitaire (réutilisé par les profils) -------------------------

    def grep(self, pattern: str, flags: int = 0) -> list[tuple[str, int, str]]:
        """Grep interne renvoyant (fichier, ligne, texte) pour un motif.

        Utilisé par les profils pour cartographier une couche (ex. accès JDBC
        du profil Java/NetBeans, §4.6). Lecture seule, aucun sous-processus.
        """
        rx = re.compile(pattern, flags)
        hits: list[tuple[str, int, str]] = []
        for f in self.source_files():
            lines = self._read_lines(os.path.join(self.repo, f.path))
            for i, line in enumerate(lines, start=1):
                if rx.search(line):
                    hits.append((f.path, i, line.strip()))
        return hits
