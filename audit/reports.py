"""Génération des livrables (§5), lecture seule sur un `AuditResult`.

Trois rapports, un seul état analysé (§ model.py) — jamais de recalcul ici,
uniquement du *rendu* :

- `human_report` (§5.1) : mémo de reprise en main pour Alain.
- `ai_report_with_repo` (§5.2) : carte compacte pour une IA qui lira le code.
- `ai_report_without_repo` (§5.3) : même carte + extraits de code réels.

Toutes trois respectent la règle de concision §5.4 : un point d'attention =
une ligne au format `chemin:ligne — [type] description`, plafonné par
catégorie, avec mention explicite « N sur M » quand le plafond est atteint.
Aucune suggestion de correctif (§5.4) : on nomme, on n'ordonne pas.
"""

from __future__ import annotations

from .model import (
    AuditResult,
    Finding,
    Layer,
    LayerState,
)

# Plafond par catégorie de point d'attention (§5.4).
FINDINGS_CAP = 10

# Ordre d'affichage stable des couches.
_LAYER_ORDER = (Layer.PERSISTENCE, Layer.BUSINESS, Layer.VIEW, Layer.UNKNOWN)


# --- règle de concision §5.4 -----------------------------------------------

def _capped_lines(findings: list[Finding], cap: int = FINDINGS_CAP) -> list[str]:
    """Rend les findings groupés par catégorie, chaque catégorie plafonnée (§5.4).

    Tri par `score` décroissant (fan-in / taille) pour ne garder que les
    occurrences les plus significatives. Quand une catégorie dépasse le
    plafond, on l'annonce explicitement (« 10 sur 34 occurrences détectées »)
    pour ne pas masquer la troncature.
    """
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.kind, []).append(f)

    lines: list[str] = []
    for kind in sorted(groups, key=lambda k: -max(f.score for f in groups[k])):
        items = sorted(groups[kind], key=lambda f: f.score, reverse=True)
        for f in items[:cap]:
            lines.append(f"- {f.render()}")
        if len(items) > cap:
            lines.append(
                f"  … {cap} sur {len(items)} occurrences détectées pour "
                f"[{kind}] (les plus significatives, triées par taille/fan-in)"
            )
    return lines


def _real_findings(result: AuditResult) -> list[Finding]:
    """Points d'attention « dette / pièges », hors marqueurs TODO purement informatifs."""
    return [f for f in result.findings if f.kind != "TODO"]


def _todos(result: AuditResult) -> list[Finding]:
    return [f for f in result.findings if f.kind == "TODO"]


# --- fragments partagés ----------------------------------------------------

def _tech_identity_block(result: AuditResult) -> list[str]:
    """Section « Identité technique du projet » (§5.2)."""
    t = result.tech
    out = ["## Identité technique du projet", ""]
    out.append(f"- Langage : {t.language}")
    out.append(f"- Framework(s) : {', '.join(t.frameworks) if t.frameworks else '—'}")
    out.append(f"- Gestion des dépendances : {t.dependency_manager}")
    if t.main_dependencies:
        out.append("- Dépendances principales :")
        out.extend(f"  - {dep}" for dep in t.main_dependencies)
    else:
        out.append("- Dépendances principales : —")
    out.append(
        f"- Point(s) d'entrée : {', '.join(t.entry_points) if t.entry_points else '—'}"
    )
    out.append(f"- Commande de lancement : {t.run_command or '—'}")
    if t.readme_excerpt:
        out += ["", "### Extrait du README", "", "> " + t.readme_excerpt.replace("\n", "\n> ")]
    else:
        out += ["", "_Aucun README repéré._"]
    return out


def _inventory_by_layer(result: AuditResult) -> list[str]:
    """Inventaire des fichiers par couche, une ligne de description chacun (§5.2)."""
    out = ["## Inventaire par couche", ""]
    for layer in _LAYER_ORDER:
        files = sorted(result.files_by_layer(layer), key=lambda f: f.loc, reverse=True)
        if not files:
            continue
        state = result.layers.get(layer)
        state_txt = f" — état : {state.value}" if state else ""
        out.append(f"### Couche {layer.value}{state_txt} ({len(files)} fichier(s))")
        for f in files[:20]:
            reason = f" ({f.layer_reason})" if f.layer_reason else ""
            out.append(f"- `{f.path}` — {f.loc} lignes{reason}")
        if len(files) > 20:
            out.append(f"  … {20} sur {len(files)} fichiers de cette couche")
        out.append("")
    return out


def _conventions_block(result: AuditResult) -> list[str]:
    out = ["## Conventions repérées", ""]
    if result.conventions:
        out += [f"- {c}" for c in result.conventions]
    else:
        out.append("- Aucune convention de nommage reconnue — repérage par taille/densité/fan-in.")
    return out


def _traps_block(result: AuditResult) -> list[str]:
    """Pièges connus, format §5.4 (chemin:ligne — [type] description)."""
    out = ["## Pièges connus / dette technique", ""]
    real = _real_findings(result)
    if real:
        out += _capped_lines(real)
    else:
        out.append("- Aucun point d'attention automatique remonté.")
    return out


def _todo_block(result: AuditResult) -> list[str]:
    out = ["## TODO / incohérences à vérifier", ""]
    todos = _todos(result)
    if todos:
        out += _capped_lines(todos)
    else:
        out.append("- Aucun marqueur TODO/FIXME repéré.")
    # Couches attendues mais vides = incohérence à vérifier.
    missing = [
        layer.value
        for layer, state in result.layers.items()
        if state == LayerState.INCOMPLETE
    ]
    if missing:
        out.append(
            f"- Couche(s) sans fichier identifié : {', '.join(missing)} — "
            "à confirmer (peut être normal, ou couche réellement absente)."
        )
    return out


def _entry_points_block(result: AuditResult) -> list[str]:
    t = result.tech
    out = ["## Points d'entrée", ""]
    if t.entry_points:
        out += [f"- `{ep}`" for ep in t.entry_points]
    else:
        out.append("- Aucun point d'entrée évident repéré.")
    out.append(f"- Lancement suggéré : `{t.run_command}`" if t.run_command else "- Lancement : indéterminé")
    return out


def _dynamic_block(result: AuditResult) -> list[str]:
    """Section « Pistes de vérification dynamique » (§6). Rendue si présente."""
    out = ["## Pistes de vérification dynamique (§6 — non exécutées)", ""]
    if not result.dynamic_checks:
        out.append("- Aucune piste générée (composant §6 non branché).")
        return out
    out.append(
        "_Commandes **suggérées**, jamais lancées par l'audit. Chacune tranche "
        "un doute qui exigerait une exécution réelle._"
    )
    out.append("")
    for c in result.dynamic_checks:
        out.append(f"- `{c.command}`")
        out.append(f"  → {c.doubt}")
    return out


def _verdict_block(result: AuditResult) -> list[str]:
    """Verdict qualitatif formateur (§8). Rendu s'il a été calculé."""
    out = ["## Verdict qualitatif formateur (§8)", ""]
    v = result.verdict
    if v is None:
        out.append("- Verdict non calculé (composant §8 non branché).")
        return out
    out.append(f"**{v.positioning()}**")
    out.append("")
    out.append(f"- Complexité conceptuelle — {v.complexity_reason}")
    out.append(f"- Qualité d'exécution — {v.execution_reason}")
    out.append("")
    forts = [p for p in v.points if p.positive]
    faibles = [p for p in v.points if not p.positive]
    if forts:
        out.append("### Points forts")
        out += [f"- {p.render()}" for p in forts]
        out.append("")
    if faibles:
        out.append("### Points à retravailler")
        out += [f"- {p.render()}" for p in faibles]
        out.append("")
    return out


# --- §5.1 rapport humain ---------------------------------------------------

def _executive_summary(result: AuditResult) -> list[str]:
    """Résumé exécutif 3-4 lignes : santé globale + effort estimé (§5.1)."""
    n_files = len(result.files)
    total_loc = sum(f.loc for f in result.files)
    real = _real_findings(result)
    monoliths = [f for f in real if f.kind == "fichier monolithique"]

    if result.verdict is not None:
        health = (
            f"exécution jugée « {result.verdict.execution.value} », "
            f"complexité « {result.verdict.complexity.value} »"
        )
    elif not real:
        health = "aucun signal d'alerte automatique"
    else:
        health = f"{len(real)} point(s) d'attention repéré(s)"

    # Effort de reprise : grossier, dérivé du volume et de la concentration.
    if n_files == 0:
        effort = "indéterminé (aucun fichier source retenu)"
    elif len(monoliths) >= 5 or total_loc > 20000:
        effort = "conséquent (volume important et/ou plusieurs fichiers monolithiques)"
    elif len(monoliths) >= 1 or real:
        effort = "modéré (quelques zones denses à reprendre en main)"
    else:
        effort = "faible (structure lisible à première vue)"

    return [
        "## Résumé exécutif",
        "",
        f"- Profil détecté : **{result.profile_name}** ({result.profile_detection_reason}).",
        f"- Périmètre : {n_files} fichier(s) source, ~{total_loc} lignes.",
        f"- État de santé global : {health}.",
        f"- Effort estimé pour relancer : {effort}.",
        "",
        "_Aide accessoire à la décision « reprendre ou archiver » — pas un objectif premier (§5.1)._",
    ]


def _layer_states_block(result: AuditResult) -> list[str]:
    out = ["## État par couche", ""]
    for layer in (Layer.PERSISTENCE, Layer.BUSINESS, Layer.VIEW):
        state = result.layers.get(layer, LayerState.UNKNOWN)
        n = len(result.files_by_layer(layer))
        note = ""
        if state == LayerState.UNKNOWN:
            note = " — « fonctionnel/cassé » indécidable sans exécution (voir pistes §6)"
        elif state == LayerState.INCOMPLETE:
            note = " — aucun fichier rattaché"
        out.append(f"- **{layer.value}** : {state.value} ({n} fichier(s)){note}")
    return out


def _next_steps_block(result: AuditResult) -> list[str]:
    """Prochaines étapes classées par priorité (§5.1). Dérivées, non prescriptives sur le code."""
    out = ["## Prochaines étapes suggérées (par priorité)", ""]
    steps: list[str] = []

    if result.dynamic_checks:
        first = result.dynamic_checks[0].command
        steps.append(
            f"1. Lever les doutes d'exécution via les pistes §6 (ex. `{first}`) "
            "avant tout jugement sur ce qui « marche »."
        )
    real = _real_findings(result)
    monoliths = [f for f in real if f.kind == "fichier monolithique"]
    if monoliths:
        biggest = max(monoliths, key=lambda f: f.score)
        steps.append(
            f"2. Cartographier les fichiers monolithiques en priorité "
            f"(le plus gros : `{biggest.path}`) — ce sont les nœuds de reprise."
        )
    if any(f.kind == "SQL fragile" for f in real):
        steps.append(
            "3. Recenser les accès données fragiles signalés (SQL par concaténation) "
            "avant toute évolution du schéma — décision de correctif laissée à Alain (§5.4)."
        )
    if any(f.kind == "absence de tests" for f in result.findings):
        steps.append(
            f"{len(steps) + 1}. Absence de filet de tests : prévoir une vérification "
            "manuelle des parcours critiques identifiés."
        )
    if not steps:
        steps.append("1. Confirmer par lecture ciblée les fichiers à fort fan-in (cœur probable).")
    out += steps
    return out


def human_report(result: AuditResult) -> str:
    """Rapport humain (§5.1) : mémo de reprise en main pour Alain."""
    parts: list[list[str]] = [
        [f"# Rapport de reprise en main — `{result.repo_path}`", ""],
        _executive_summary(result),
        _layer_states_block(result),
        _traps_block(result),
        _next_steps_block(result),
        _entry_points_block(result),
        _verdict_block(result),
        _dynamic_block(result),
    ]
    return _join(parts)


# --- §5.2 rapport IA avec accès repo ---------------------------------------

def ai_report_with_repo(result: AuditResult) -> str:
    """Rapport IA « avec accès repo » (§5.2) : une carte compacte, pas un cours."""
    parts: list[list[str]] = [
        [f"# Carte du projet (IA, accès repo) — `{result.repo_path}`", "",
         "_Compact volontairement : l'IA destinataire ira lire le détail elle-même (§5.2)._", ""],
        _tech_identity_block(result),
        _inventory_by_layer(result),
        _entry_points_block(result),
        _conventions_block(result),
        _traps_block(result),
        _todo_block(result),
        _verdict_block(result),
        _dynamic_block(result),
    ]
    return _join(parts)


# --- §5.3 rapport IA sans accès repo ---------------------------------------

def _excerpts_block(result: AuditResult) -> list[str]:
    """Extraits de code réels aux points d'architecture / problèmes (§5.3)."""
    out = ["## Extraits de code (points d'architecture & problèmes)", ""]
    if not result.excerpts:
        out.append("_Aucun extrait retenu._")
        return out
    for ex in result.excerpts:
        out.append(f"### `{ex.path}` (à partir de la ligne {ex.start_line}) — {ex.caption}")
        out.append("```")
        for offset, line in enumerate(ex.lines):
            out.append(f"{ex.start_line + offset:>5}  {line}")
        out.append("```")
        out.append("")
    return out


def ai_report_without_repo(result: AuditResult) -> str:
    """Rapport IA « sans accès repo » (§5.3) : même squelette + extraits réels."""
    parts: list[list[str]] = [
        [f"# Dossier du projet (IA, sans accès repo) — `{result.repo_path}`", "",
         "_Même carte que la variante « avec accès repo », enrichie d'extraits de "
         "code réels : l'IA destinataire n'a pas accès au dépôt (§5.3)._", ""],
        _tech_identity_block(result),
        _inventory_by_layer(result),
        _entry_points_block(result),
        _conventions_block(result),
        _traps_block(result),
        _todo_block(result),
        _excerpts_block(result),
        _verdict_block(result),
        _dynamic_block(result),
    ]
    return _join(parts)


# --- assemblage ------------------------------------------------------------

def _join(parts: list[list[str]]) -> str:
    blocks = ["\n".join(section) for section in parts]
    return "\n\n".join(blocks).rstrip() + "\n"
