"""Profil générique (fallback) — heuristiques §4.1–4.4 seules (§4.6).

Aucune convention de nommage n'est présumée : tous les fichiers restent en
couche `UNKNOWN`, et ce sont les heuristiques brutes (taille, densité,
fan-in) qui portent le repérage. C'est le filet de sécurité quand aucun
profil spécifique ne reconnaît le dépôt.
"""

from __future__ import annotations

from .base import Profile

GENERIC = Profile()
