# Azure Functions — validation du 22 octobre 2026

## Ressources déployées

- Groupe : `rg-riftlab-dev`, région France Central.
- Application : `func-riftlab-dev-023139`, Python 3.12, Flex Consumption,
  mémoire de 512 Mo, aucune instance always-ready configurée.
- Stockage interne du runtime et de sa queue : `striftlabfunc023139`.
- Application Insights : `func-riftlab-dev-023139`.
- Stockage RAW existant : `striftlabdev01`, conteneur `riot-raw`.
- Identité système de la Function App : rôle `Storage Blob Data Contributor`
  attribué au niveau du seul conteneur RAW pour le code d'ingestion.

Le runtime et la queue utilisent leur propre configuration `AzureWebJobsStorage`.
Cette configuration interne est distincte de l'accès du code métier à Blob par
identité managée. Les paramètres Riot sont dans Application Settings. Aucun secret
ni fichier de données locales n'est inclus dans le ZIP de 9 fichiers.

## Recette réelle

Le lancement via `scripts.invoke_function` a vérifié les points suivants :

| Contrôle | Résultat |
| --- | --- |
| POST sans clé Functions | Refus HTTP 401 |
| POST protégé, limite 3 matchs | HTTP 202, identifiant de demande retourné |
| Traitement asynchrone par queue | Terminé en `SUCCESS` |
| Découverte Riot depuis Azure | 3 matchs |
| Payloads récupérés dans le répertoire temporaire cloud | 3 matchs et 3 timelines |
| Écritures nouvelles dans Blob | 6, aucune erreur |
| Publication et relecture du manifest | Réussies |
| Consultation HTTP du résultat final | HTTP 200, `SUCCESS` |
| Inventaire distant après traitement | 53 matchs et 53 timelines |
| Fonctions indexées dans Azure | `start_ingestion`, `ingest_worker`, `ingestion_status` |
| Application Insights | 10 traces corrélées au run, dont `manifest_saved` et `run_finished` en `SUCCESS` |
| Vérifications locales | 31 tests réussis, Ruff réussi |

Demande : `17a33bc646334e9da3bce2eff0f6fe59`.

Run : `20261022T110617Z-135c7cdb7d0945ba94656e92dabf3fa3`.

Manifest dans `riot-raw` :
`manifests/run_id=20261022T110617Z-135c7cdb7d0945ba94656e92dabf3fa3/manifest.json`.

Résultat de la demande : `requests/17a33bc646334e9da3bce2eff0f6fe59.json`.
Une copie locale du manifest est conservée dans
`data/validation/azure_function_run.json`, exclue de Git.

Requête KQL utilisée dans Application Insights :

```kusto
traces
| where timestamp > ago(1h)
| where message has "20261022T110617Z-135c7cdb7d0945ba94656e92dabf3fa3"
| project timestamp, message
| order by timestamp asc
```

Les 6 nouveaux blobs proviennent d'Azure et ne sont pas téléchargés dans les
répertoires locaux `data/matches` et `data/timelines`. L'audit exhaustif comparant
Azure à ces répertoires signalera donc ces fichiers supplémentaires attendus.

## Exploitation et limites

- Aucun timer quotidien : lancer manuellement avec une clé Riot valide.
- Mettre à jour Application Settings après chaque changement de clé Riot ; le
  script de déploiement transfère la valeur locale sans l'afficher.
- Garder un seul lot actif pour le quota Riot partagé. La configuration de queue
  limite la concurrence par instance, pas à l'échelle de toute l'application.
- Un répertoire temporaire cloud n'est pas un checkpoint durable. Après un arrêt
  forcé, examiner les logs et `riftlab-ingestion-poison`, puis relancer.
- Les échecs métier terminés sont publiés avec un statut explicite. Les erreurs
  techniques non récupérées vont en queue poison après une tentative.
- Le budget Azure, les alertes opérationnelles et les tableaux de bord détaillés
  restent au chantier de supervision.

## Références

- [Flex Consumption : création et déploiement](https://learn.microsoft.com/en-us/azure/azure-functions/flex-consumption-how-to).
- [Modèle Python v2](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python).
- [Configuration des bindings Azure Queue](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue).
