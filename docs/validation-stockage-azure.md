# Validation du stockage Azure — 22 octobre 2026

Vérification effectuée sur le conteneur `riot-raw` via la session Azure CLI locale.

| Contrôle réel | Résultat |
| --- | --- |
| Accès public du conteneur | Désactivé (`public_access = null`) |
| Inventaire distant | 50 matchs et 50 timelines |
| JSON locaux | 100 valides selon le validateur minimal du projet |
| Appariement local | 50 paires match/timeline |
| Blobs manquants ou supplémentaires dans les deux préfixes | 0 |
| Téléchargement et comparaison SHA-256 | 100 fichiers identiques aux fichiers locaux |
| Relance de l'upload | 0 upload, 100 skips après vérification, 0 JSON invalide, 0 échec |
| Tests Python | 8 réussis, dont refus d'un blob existant différent |
| Ruff sur les fichiers Python modifiés ou ajoutés | Réussi |

Le rapport détaillé de l'audit est conservé localement dans
`data/validation/azure_storage_validation.json` et exclu de Git.
Les commandes de reproduction figurent dans le README.

Le contrôle porte sur les octets des objets et sur la validation minimale du JSON.
Il ne constitue pas une validation exhaustive du schéma Riot, du réseau Azure ou
des politiques IAM. La reprise après interruption et le manifest d'exécution
restent à construire au jalon suivant.
