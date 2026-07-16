"""Orchestrateur d'analyse — le « Chef » qui assemble un `AuditResult` (§3).

Enchaîne : détection de profil (§4.5) → moteur d'heuristiques (§4.1–4.4) →
étiquetage des couches par convention → repérage transversal (findings §5.4,
extraits §5.3, identité technique §5.2). Le verdict (§8) et les pistes
dynamiques (§6) sont ajoutés par leurs modules respectifs (`verdict.py`,
`dynamic.py`) pour garder chaque composant isolé.

Aucune exécution : tout est déduit par lecture (§2). L'état « fonctionnel /
cassé » d'une couche n'est *pas* décidable sans exécution — on le laisse
honnêtement « indéterminé » et on renvoie le doute vers les pistes §6.
"""

from __future__ import annotations

import os

from .engine import Heuristics
from .model import (
    AuditResult,
    Excerpt,
    FileInfo,
    Finding,
    Layer,
    LayerState,
)
from .profiles import detect_profile
from .profiles.base import Profile

# Seuil « fichier monolithique » (§8.1) : au-delà, un fichier concentre trop.
MONOLITH_LOC = 400


def run_audit(repo_path: str, forced_profile: str = "auto") -> AuditResult:
    """Analyse complète d'un dépôt en lecture seule. Renvoie l'`AuditResult`."""
    repo_path = os.path.abspath(repo_path)
    profile, reason = detect_profile(repo_path, forced_profile)

    h = profile.make_heuristics(repo_path)
    files = h.source_files()
    profile.classify(h, files)  # §4.5 : étiquetage par convention

    result = AuditResult(
        repo_path=repo_path,
        profile_name=profile.name,
        profile_detection_reason=reason,
        files=files,
        large_files=h.large_files(),
        dense_dirs=h.dense_dirs(),
        fan_in=h.fan_in(),
        conventions=profile.conventions(h, files),
        tech=profile.tech_identity(h),
    )
    result.layers = _layer_states(files)
    result.findings = _collect_findings(profile, h, files)
    result.excerpts = _build_excerpts(h, result)
    return result


def _layer_states(files: list[FileInfo]) -> dict[Layer, LayerState]:
    """État par couche (§5.1), prudemment.

    Sans exécution, « fonctionnel / cassé » n'est pas décidable : une couche
    dont on a trouvé des fichiers est marquée `UNKNOWN` (à confirmer par les
    pistes §6), une couche attendue mais vide, `INCOMPLETE`.
    """
    states: dict[Layer, LayerState] = {}
    for layer in (Layer.PERSISTENCE, Layer.BUSINESS, Layer.VIEW):
        has_files = any(f.layer == layer for f in files)
        states[layer] = LayerState.UNKNOWN if has_files else LayerState.INCOMPLETE
    return states


def _has_tests(files: list[FileInfo]) -> bool:
    return any(
        seg in ("test", "tests", "spec", "specs", "__tests__")
        for f in files
        for seg in f.path.split(os.sep)
    )


def _collect_findings(
    profile: Profile, h: Heuristics, files: list[FileInfo]
) -> list[Finding]:
    """Points d'attention §5.4 : génériques + spécifiques au profil."""
    findings: list[Finding] = []

    # Fichiers monolithiques (§8.1) — pondérés pour ignorer tests/locale.
    for f in files:
        effective = f.loc * f.weight
        if effective >= MONOLITH_LOC:
            findings.append(Finding(
                path=f.path,
                line=None,
                kind="fichier monolithique",
                description=f"{f.loc} lignes — concentre probablement plusieurs responsabilités",
                layer=f.layer,
                score=float(f.loc),
            ))

    # Absence de tests (§8.1) — un seul point, non chiffré.
    if not _has_tests(files):
        findings.append(Finding(
            path=".",
            line=None,
            kind="absence de tests",
            description="aucun dossier de tests repéré",
            score=MONOLITH_LOC,  # significatif, remonte dans le tri
        ))

    # Spécifiques à la techno (ex. SQL par concaténation du profil Java).
    findings.extend(profile.findings(h, files))
    return findings


def _build_excerpts(h: Heuristics, result: AuditResult) -> list[Excerpt]:
    """Extraits de code réels pour le rapport « sans accès repo » (§5.3).

    Volontairement borné : le plus gros fichier de chaque couche identifiée
    (point d'architecture pivot) + le contexte de chaque point d'attention
    portant une ligne — pas de couverture exhaustive (§5.3).
    """
    excerpts: list[Excerpt] = []
    seen: set[tuple[str, int]] = set()

    def add(path: str, line: int, caption: str, radius: int = 4) -> None:
        key = (path, line)
        if key in seen:
            return
        seen.add(key)
        lines = h._read_lines(os.path.join(h.repo, path))
        start = max(1, line - radius)
        end = min(len(lines), line + radius)
        excerpts.append(Excerpt(
            path=path,
            start_line=start,
            lines=lines[start - 1:end],
            caption=caption,
        ))

    # Pivot par couche : le plus gros fichier étiqueté de chaque couche.
    for layer in (Layer.PERSISTENCE, Layer.BUSINESS, Layer.VIEW):
        layer_files = [f for f in result.files if f.layer == layer]
        if layer_files:
            pivot = max(layer_files, key=lambda f: f.loc)
            add(pivot.path, 1, f"Fichier pivot couche {layer.value}", radius=6)

    # Contexte de chaque point d'attention localisé (borné aux 8 premiers).
    for finding in [f for f in result.findings if f.line][:8]:
        add(finding.path, finding.line, f"[{finding.kind}] {finding.description}")

    return excerpts
