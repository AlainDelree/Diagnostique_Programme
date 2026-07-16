"""Profil Java/NetBeans artisanal (§4.6) — premier cas de test (§7).

Projet Java/MySQL ancien, fait main via NetBeans, sans Maven/Gradle, sans
ORM. Plus exigeant que les projets à conventions toutes faites : c'est le
test de robustesse du cœur généraliste.

Ce que le profil sait reconnaître :
- **Signature** : `nbproject/`, `build.xml` (Ant).
- **Vue** : paires `NomClasse.java` + `NomClasse.form` (formulaires Swing
  générés) → cartographie fiable des écrans.
- **Persistance** : JDBC brut (`DriverManager`, `Connection`, `Statement`,
  `ResultSet`, SQL littéral) → accès MySQL. Les requêtes construites par
  concaténation de chaînes sont signalées en point d'attention (§5.4),
  *sans* suggestion de correctif.
- **Dépendances** : `nbproject/project.xml` et/ou `lib/*.jar` nommés.
- **Métier** : par élimination, souvent appelé depuis les gestionnaires
  d'événements (`jButtonXActionPerformed`) — recoupe le fan-in (§4.3).
"""

from __future__ import annotations

import os
import re

from ..engine import Heuristics
from ..model import FileInfo, Finding, Layer, TechIdentity
from .base import Profile, exists, read_readme

# Marqueurs JDBC bruts : leur présence dans un fichier trahit un accès BD.
_JDBC_MARKERS = re.compile(
    r"\b(DriverManager|getConnection|(?:Prepared|Callable)?Statement|ResultSet|"
    r"executeQuery|executeUpdate)\b"
)

# SQL en littéral (pour repérer les fichiers d'accès et les requêtes fragiles).
_SQL_LITERAL = re.compile(
    r'"[^"]*\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN)\b', re.IGNORECASE
)

# Requête construite par concaténation : chaîne SQL suivie d'un `+` (variable
# injectée directement). Signal de fragilité (§5.4) — jamais de correctif ici.
_SQL_CONCAT = re.compile(
    r'"[^"]*\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)\b[^"]*"\s*\+',
    re.IGNORECASE,
)

# Gestionnaire d'événement Swing généré par NetBeans (indice de couche Vue).
_EVENT_HANDLER = re.compile(r"\bj\w+ActionPerformed\b")


class JavaNetBeansProfile(Profile):
    name = "java-netbeans"
    language = "Java"
    source_extensions = frozenset({".java", ".xml", ".properties", ".sql"})
    # Java-like : capte les définitions de méthodes pour le fan-in (§4.3).
    func_def_patterns = (
        r"^\s*(?:public|private|protected|static|final|synchronized|\s)+"
        r"[\w<>\[\].]+\s+([A-Za-z_]\w+)\s*\([^;{]*\)\s*(?:throws[\w,\s.]+)?\{",
    )

    # -- détection (§4.6) ----------------------------------------------------

    def matches(self, repo_path: str) -> tuple[bool, str]:
        has_nbproject = exists(repo_path, "nbproject")
        has_ant = exists(repo_path, "build.xml")
        if has_nbproject and has_ant:
            return True, "nbproject/ + build.xml (signature NetBeans/Ant)"
        if has_nbproject:
            return True, "présence de nbproject/ (signature NetBeans)"
        return False, ""

    # -- paires .java/.form (Vue) -------------------------------------------

    def _form_stems(self, repo_path: str) -> set[str]:
        """Chemins (sans extension) ayant un `.form` NetBeans à côté du `.java`.

        Les `.form` ne sont pas comptés comme source ; on les repère par un
        parcours dédié pour cartographier les écrans Swing.
        """
        stems: set[str] = set()
        for root, dirs, names in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("build", "dist")]
            for name in names:
                if name.endswith(".form"):
                    abs_stem = os.path.join(root, name[:-5])
                    stems.add(os.path.relpath(abs_stem, repo_path))
        return stems

    def classify(self, h: Heuristics, files: list[FileInfo]) -> None:
        form_stems = self._form_stems(h.repo)
        # Fichiers touchant JDBC (grep unique, réutilisé pour la persistance).
        jdbc_files = {
            path for path, _line, _txt in h.grep(_JDBC_MARKERS.pattern)
        } | {
            path for path, _line, _txt in h.grep(_SQL_LITERAL.pattern)
        }

        for f in files:
            stem = f.path[:-5] if f.path.endswith(".java") else None
            if stem and stem in form_stems:
                f.layer = Layer.VIEW
                f.layer_reason = "formulaire Swing (paire .java/.form)"
            elif f.path in jdbc_files:
                f.layer = Layer.PERSISTENCE
                f.layer_reason = "accès JDBC brut (DriverManager/Statement/SQL)"
            # Sinon : couche laissée indéterminée → repérée par fan-in/taille
            # (§4.3), souvent du métier appelé depuis les écrans.

    # -- points d'attention SQL (§5.4) --------------------------------------

    def findings(self, h: Heuristics, files: list[FileInfo]) -> list[Finding]:
        loc_by_path = {f.path: f.loc for f in files}
        layer_by_path = {f.path: f.layer for f in files}
        out: list[Finding] = []
        for path, line, _txt in h.grep(_SQL_CONCAT.pattern):
            out.append(Finding(
                path=path,
                line=line,
                kind="SQL fragile",
                description="requête construite par concaténation de chaînes",
                layer=layer_by_path.get(path, Layer.UNKNOWN),
                # Score = taille du fichier : les gros fichiers d'accès priment
                # au moment d'appliquer le plafond §5.4.
                score=float(loc_by_path.get(path, 0)),
            ))
        return out

    # -- conventions & identité technique -----------------------------------

    def conventions(self, h: Heuristics, files: list[FileInfo]) -> list[str]:
        found: list[str] = []
        forms = self._form_stems(h.repo)
        if forms:
            found.append(
                f"Écrans Swing cartographiés via paires .java/.form ({len(forms)} formulaire(s))"
            )
        if any(f.layer == Layer.PERSISTENCE for f in files):
            found.append("Accès données via JDBC brut (pas d'ORM) — cartographié par grep")
        if h.grep(_EVENT_HANDLER.pattern):
            found.append(
                "Logique appelée depuis des gestionnaires d'événements Swing "
                "(jXxxActionPerformed) — recoupe le fan-in (§4.3)"
            )
        return found

    def _jar_dependencies(self, repo_path: str) -> list[str]:
        jars: list[str] = []
        lib = os.path.join(repo_path, "lib")
        if os.path.isdir(lib):
            for name in sorted(os.listdir(lib)):
                if name.endswith(".jar"):
                    jars.append(f"lib/{name}")
        return jars

    def tech_identity(self, h: Heuristics) -> TechIdentity:
        repo = h.repo
        jars = self._jar_dependencies(repo)
        dep_manager = "Ant (build.xml)" if exists(repo, "build.xml") else "manuel (lib/*.jar)"
        entry_points: list[str] = []
        # Point d'entrée : classe avec `public static void main`.
        for path, line, _txt in h.grep(r"public\s+static\s+void\s+main\s*\("):
            entry_points.append(f"{path}:{line}")
        return TechIdentity(
            language="Java",
            frameworks=["Swing (NetBeans GUI Builder)", "JDBC/MySQL"],
            dependency_manager=dep_manager,
            main_dependencies=jars,
            readme_excerpt=read_readme(repo),
            entry_points=entry_points[:5],
            run_command="ant run  (ou exécuter la classe portant main() depuis NetBeans)",
        )


JAVA_NETBEANS = JavaNetBeansProfile()
