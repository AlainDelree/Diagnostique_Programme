"""Modèle de données partagé par tout l'outil d'audit.

Toute l'analyse (moteur d'heuristiques, profils, verdict) remplit un objet
`AuditResult` unique ; les générateurs de rapports (§5) ne font ensuite que
le *rendre*. Séparer l'analyse du rendu évite de recalculer et garantit que
les trois rapports décrivent exactement le même état.

Le format des « points d'attention » (`Finding`) est volontairement
catégorisable — `[type]` explicite — pour rester compatible avec une future
mémoire de patterns récurrents (§8.4) sans refactor rétroactif.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Layer(str, Enum):
    """Les trois couches d'une application, plus l'inconnu.

    Reprend le découpage §3 (Persistance / Métier / Vue). `UNKNOWN` couvre
    les fichiers qu'aucune convention ni heuristique n'a su rattacher.
    """

    PERSISTENCE = "persistance"
    BUSINESS = "métier"
    VIEW = "vue"
    UNKNOWN = "indéterminée"


class LayerState(str, Enum):
    """État constaté d'une couche, tel que rendu dans le rapport humain (§5.1)."""

    FUNCTIONAL = "fonctionnel"
    BROKEN = "cassé"
    INCOMPLETE = "incomplet"
    UNKNOWN = "indéterminé"


@dataclass
class FileInfo:
    """Un fichier source retenu par le moteur (après exclusions §4.4).

    `weight` (0..1) permet de dé-pondérer sans exclure totalement les
    fichiers de test/locale (§4.4) : ils comptent, mais moins que du métier.
    """

    path: str  # relatif à la racine du dépôt audité
    loc: int  # lignes de code (approximation `wc -l`)
    ext: str
    layer: Layer = Layer.UNKNOWN
    layer_reason: str = ""  # "via convention DAO", "par fan-in", ...
    weight: float = 1.0
    # Bibliothèque tierce *embarquée* dans les sources (vendored) : code non
    # écrit par l'auteur du projet (ex. `com.toedter.*` glissé dans `src/`).
    # Isolé des classements taille/fan-in/duplication et regroupé à part (§4.6).
    vendored: bool = False
    package_root: str = ""  # racine de package déduite (Java) — sert au regroupement


@dataclass
class Finding:
    """Un point d'attention, format fixe §5.4 : `chemin:ligne — [type] desc`.

    `kind` est le `[type]` catégorisable (§8.4). `score` sert au tri quand
    une catégorie dépasse son plafond (§5.4) — plus il est haut, plus le
    point est significatif (dérivé du fan-in / de la taille).
    """

    path: str
    line: int | None
    kind: str  # ex. "SQL fragile", "fichier monolithique", "absence de tests"
    description: str
    layer: Layer = Layer.UNKNOWN
    score: float = 0.0

    def render(self) -> str:
        """Rend la ligne canonique §5.4."""
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"{loc} — [{self.kind}] {self.description}"


@dataclass
class Excerpt:
    """Extrait de code réel, pour le rapport IA « sans accès repo » (§5.3)."""

    path: str
    start_line: int
    lines: list[str]
    caption: str  # pourquoi cet extrait est central / à quel problème il se rattache


@dataclass
class DynamicCheck:
    """Une piste de vérification dynamique (§6) : commande + doute tranché.

    `command` n'est *jamais* exécutée par l'outil ; elle est seulement
    suggérée, reliée au doute qu'elle permettrait de lever.
    """

    command: str
    doubt: str
    layer: Layer = Layer.UNKNOWN


# --- Verdict qualitatif (§8) ------------------------------------------------

class ConceptualComplexity(str, Enum):
    """Axe « complexité conceptuelle » (§8.3), échelle nommée et stable (§8.4)."""

    SIMPLE = "simple"
    MODEREE = "modérée"
    AMBITIEUSE = "ambitieuse"


class ExecutionQuality(str, Enum):
    """Axe « qualité d'exécution » (§8.3), échelle nommée et stable (§8.4)."""

    FRAGILE = "fragile"
    PERFECTIBLE = "perfectible"
    SOLIDE = "solide"
    IMPECCABLE = "impeccable"


@dataclass
class VerdictPoint:
    """Un point du verdict, positif ou négatif, formulé « constat + pourquoi » (§8.2).

    `kind` est le type catégorisable (§8.4). `positive` distingue point fort
    et point faible. `why` porte l'explication pédagogique : c'est elle qui
    fait apprendre, jamais le constat seul (§8.2).
    """

    kind: str  # ex. "SQL en dur", "absence de tests", "séparation Vue/Métier"
    positive: bool
    observation: str  # le constat
    why: str  # pourquoi c'est un problème (ou un bénéfice)

    def render(self) -> str:
        return f"[{self.kind}] {self.observation} — {self.why}"


@dataclass
class Verdict:
    """Verdict qualitatif formateur complet (§8). Jamais de note chiffrée (§8.3)."""

    complexity: ConceptualComplexity
    execution: ExecutionQuality
    complexity_reason: str
    execution_reason: str
    points: list[VerdictPoint] = field(default_factory=list)

    def positioning(self) -> str:
        """Phrase de positionnement croisé (§8.3)."""
        return (
            f"Complexité conceptuelle : {self.complexity.value} — "
            f"Qualité d'exécution : {self.execution.value}"
        )


# --- Agrégat central --------------------------------------------------------

@dataclass
class TechIdentity:
    """Identité technique du projet (§5.2), remplie par le profil détecté."""

    language: str = "indéterminé"
    frameworks: list[str] = field(default_factory=list)
    dependency_manager: str = "indéterminé"
    main_dependencies: list[str] = field(default_factory=list)
    readme_excerpt: str = ""
    entry_points: list[str] = field(default_factory=list)
    run_command: str = ""


@dataclass
class AuditResult:
    """Tout l'état d'un audit. Rempli par l'analyse, rendu par les rapports."""

    repo_path: str
    profile_name: str = "générique"
    profile_detection_reason: str = ""

    files: list[FileInfo] = field(default_factory=list)
    large_files: list[FileInfo] = field(default_factory=list)  # §4.1
    dense_dirs: list[tuple[str, int]] = field(default_factory=list)  # §4.2
    fan_in: list[tuple[str, int]] = field(default_factory=list)  # §4.3, approximatif

    layers: dict[Layer, LayerState] = field(default_factory=dict)
    conventions: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    excerpts: list[Excerpt] = field(default_factory=list)
    dynamic_checks: list[DynamicCheck] = field(default_factory=list)

    tech: TechIdentity = field(default_factory=TechIdentity)
    verdict: Verdict | None = None

    def files_by_layer(self, layer: Layer) -> list[FileInfo]:
        # Le code vendored (bibliothèque tierce embarquée) n'appartient à
        # aucune couche du projet : il est présenté à part (§4.6).
        return [f for f in self.files if f.layer == layer and not f.vendored]

    def project_files(self) -> list[FileInfo]:
        """Fichiers du projet lui-même (hors bibliothèques tierces embarquées)."""
        return [f for f in self.files if not f.vendored]

    def vendored_files(self) -> list[FileInfo]:
        """Fichiers de bibliothèque tierce embarquée (vendored), regroupés à part (§4.6)."""
        return [f for f in self.files if f.vendored]

    def findings_by_kind(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {}
        for f in self.findings:
            out.setdefault(f.kind, []).append(f)
        return out
