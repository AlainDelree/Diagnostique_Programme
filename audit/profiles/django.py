"""Profil Django/Python (§4.6) — projets actifs à conventions bien connues.

Les conventions Django sont assez stables pour étiqueter les couches par le
seul nom de fichier (§4.5) : `models.py` → Persistance, `views.py` → Vue,
etc. On retombe sur les heuristiques brutes uniquement pour ce qui n'est pas
nommé conventionnellement.
"""

from __future__ import annotations

import os

from ..engine import Heuristics
from ..model import FileInfo, Layer, TechIdentity
from .base import Profile, exists, read_readme


class DjangoProfile(Profile):
    name = "django"
    language = "Python"
    source_extensions = frozenset({".py", ".html", ".txt", ".cfg", ".ini", ".toml"})

    # Conventions Django : nom de fichier → couche (§4.5).
    _VIEW_NAMES = {"views.py", "urls.py", "forms.py", "admin.py", "serializers.py"}
    _BUSINESS_NAMES = {"services.py", "tasks.py", "signals.py", "managers.py"}
    _PERSISTENCE_NAMES = {"models.py", "querysets.py"}

    def matches(self, repo_path: str) -> tuple[bool, str]:
        if exists(repo_path, "manage.py"):
            return True, "présence de manage.py (signature Django)"
        # settings.py + wsgi.py même sans manage.py à la racine.
        for root, _dirs, names in os.walk(repo_path):
            if "settings.py" in names and ("wsgi.py" in names or "asgi.py" in names):
                rel = os.path.relpath(root, repo_path)
                return True, f"settings.py + wsgi/asgi.py dans {rel} (signature Django)"
            if root.count(os.sep) - repo_path.count(os.sep) > 3:
                dirs_prune = _dirs
                dirs_prune[:] = []  # ne descend pas trop profond pour la détection
        return False, ""

    def layer_for(self, relpath: str) -> tuple[Layer, str] | None:
        name = os.path.basename(relpath)
        if name in self._PERSISTENCE_NAMES:
            return Layer.PERSISTENCE, f"convention Django ({name})"
        if name in self._VIEW_NAMES or relpath.endswith(".html"):
            return Layer.VIEW, f"convention Django ({name})"
        if name in self._BUSINESS_NAMES:
            return Layer.BUSINESS, f"convention Django ({name})"
        if "/migrations/" in f"/{relpath}":
            return Layer.PERSISTENCE, "dossier migrations (convention Django)"
        return None

    def conventions(self, h: Heuristics, files: list[FileInfo]) -> list[str]:
        found: list[str] = []
        names = {os.path.basename(f.path) for f in files}
        if "models.py" in names:
            found.append("Couche Persistance via convention Django (models.py)")
        if "views.py" in names or "urls.py" in names:
            found.append("Couche Vue via convention Django (views.py / urls.py)")
        if any("/migrations/" in f"/{f.path}" for f in files):
            found.append("Migrations Django présentes (schéma géré par l'ORM)")
        return found

    def tech_identity(self, h: Heuristics) -> TechIdentity:
        repo = h.repo
        deps: list[str] = []
        dep_manager = "indéterminé"
        for req in ("requirements.txt", "pyproject.toml", "Pipfile", "setup.py"):
            if exists(repo, req):
                dep_manager = req
                try:
                    with open(os.path.join(repo, req), encoding="utf-8", errors="replace") as fh:
                        deps = [
                            ln.strip() for ln in fh.read().splitlines()
                            if ln.strip() and not ln.strip().startswith("#")
                        ][:15]
                except OSError:
                    pass
                break
        entry = "manage.py" if exists(repo, "manage.py") else ""
        return TechIdentity(
            language="Python",
            frameworks=["Django"],
            dependency_manager=dep_manager,
            main_dependencies=deps,
            readme_excerpt=read_readme(repo),
            entry_points=[entry] if entry else [],
            run_command="python manage.py runserver" if entry else "",
        )


DJANGO = DjangoProfile()
