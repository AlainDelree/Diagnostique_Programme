"""Outil de diagnostic/audit de projet (Bridge_Agent).

Audit d'un dépôt tiers en **lecture seule** : cartographie des couches
(persistance / métier / vue), repérage des zones qui comptent par
heuristiques, génération de rapports (humain + IA) et verdict qualitatif
formateur.

Voir SPEC_audit_projet.md pour la spécification complète.

Cet outil ne modifie, n'installe et n'exécute jamais rien sur le dépôt
audité (§2 de la spec). La seule exception prévue — les « pistes de
vérification dynamique » (§6) — se contente de *proposer* des commandes,
sans les lancer.
"""

__version__ = "0.1.0"
