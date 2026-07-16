"""Profils par technologie (§4.5–4.6).

Un profil est essentiellement une **liste de motifs** (dossiers/fichiers à
reconnaître, exclusions, règles de couche) — pas du code métier. Le moteur
générique (§4) reste inchangé quand on ajoute un profil ; il suffit de
déposer une nouvelle instance `Profile` ici.

Ordre de détection : du plus spécifique au plus générique. Le profil
générique (fallback) matche toujours en dernier recours.
"""

from __future__ import annotations

from .base import Profile
from .generic import GENERIC
from .django import DJANGO
from .java_netbeans import JAVA_NETBEANS

# Du plus spécifique au plus générique. GENERIC doit rester en dernier.
REGISTRY: list[Profile] = [JAVA_NETBEANS, DJANGO, GENERIC]

_BY_NAME = {p.name: p for p in REGISTRY}


def detect_profile(repo_path: str, forced: str = "auto") -> tuple[Profile, str]:
    """Sélectionne le profil (§4.5). `forced` correspond au champ PROFIL_TECHNO.

    - `forced="auto"` : détection par signature, premier match gagne.
    - `forced=<nom>` : impose ce profil (ex. `java-netbeans`, `django`).

    Renvoie (profil, raison lisible).
    """
    if forced and forced != "auto":
        prof = _BY_NAME.get(forced)
        if prof is None:
            known = ", ".join(_BY_NAME)
            raise ValueError(f"Profil inconnu : {forced!r} (connus : {known})")
        return prof, f"profil imposé via PROFIL_TECHNO={forced}"

    for prof in REGISTRY:
        matched, reason = prof.matches(repo_path)
        if matched:
            return prof, reason
    return GENERIC, "aucune signature reconnue — fallback générique (§4.6)"


__all__ = ["Profile", "REGISTRY", "detect_profile", "GENERIC", "DJANGO", "JAVA_NETBEANS"]
