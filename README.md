# riftlab-ai
End-to-end Data Engineering &amp; GenAI platform for League of Legends analytics, built with Python, Riot Games API, Azure, Snowflake, dbt and Streamlit.

## Validation Azure Blob Storage

Configurer les variables Azure de `.env.example` dans `.env`, installer les dépendances
avec `uv sync`, puis ouvrir une session avec `az login` disposant des droits Blob.
Exécuter les commandes depuis la racine du dépôt :

```bash
uv run python -m scripts.validate_blob_storage --report data/validation/azure_storage_validation.json
uv run python -m scripts.upload_batch
```

La première commande lit le conteneur et compare le SHA-256 de chaque blob au fichier
local. Elle contrôle aussi les JSON locaux, les paires match/timeline, les fichiers
manquants ou supplémentaires et l'accès public du conteneur. Le rapport reste local
dans `data/`, exclu de Git. Une erreur entraîne un code de sortie non nul.

La seconde commande crée les blobs manquants sans écrasement. Un blob existant est
ignoré uniquement si son SHA-256 correspond au fichier local ; un contenu différent
est signalé comme échec. Après une ingestion complète, une relance doit produire
0 upload et autant de fichiers ignorés que de fichiers locaux valides.

Résultats du jalon : [validation du 22 octobre 2026](docs/validation-stockage-azure.md).

## Pipeline traçable

```bash
# Découverte Riot, extraction des fichiers absents/invalides et upload Azure
uv run python run_pipeline.py --max-matches 50

# Rejeu de tous les IDs trouvés dans data/matches et data/timelines, sans appel Riot
uv run python run_pipeline.py --local

# Reprise du même lot ; nouveau run, fichiers et blobs valides réutilisés
uv run python run_pipeline.py --resume-manifest data/manifests/<ancien-run-id>/manifest.json
```

Chaque lancement produit un nouveau `run_id`, des événements JSON corrélés et un
manifest local dans `data/manifests/<run_id>/manifest.json`, puis publié et relu dans
`manifests/run_id=<run_id>/manifest.json` sur Azure. Le manifest contient les chemins
et hashes, jamais les payloads, PUUID ou clés. Les compteurs `match` et `timeline`
distinguent `written`, `skipped`, `failed` et `not_processed` ; chacun de ces deux
ensembles totalise le nombre d'IDs découverts, après déduplication.

Le checkpoint local est réécrit atomiquement après chaque opération. Un Ctrl+C
pendant le traitement produit un résultat partiel ou échoué et tente la publication.
Une terminaison brutale peut laisser un checkpoint `RUNNING` uniquement local ;
relancer avec `--resume-manifest` pour reprendre exactement les IDs du lot connu.
`--local` peut aussi accompagner cette option, mais ne récupère aucun fichier absent.
La reprise requiert une seule exécution active sur le même répertoire local.

Le code de sortie vaut 0 seulement pour `SUCCESS` ; sinon il vaut 1. Une erreur
401/403 ou un quota 429 toujours refusé après retries arrête le lot et laisse les
opérations restantes à `not_processed`. Les autres erreurs d'objets permettent de
continuer le lot. Si la publication ou la relecture du manifest échoue, le résultat
local passe à `FAILED` avec `manifest_publish` ; le manifest distant peut être absent
ou refléter le bilan antérieur à cette erreur. Consulter alors le checkpoint local.

## Azure Functions

Recette cloud : [validation du 22 octobre 2026](docs/validation-azure-functions.md).

Le déploiement utilise Python 3.12 sur Flex Consumption. Une requête HTTP protégée
met le travail dans Azure Storage Queue et retourne un `request_id` (HTTP 202).
Le worker exécute le pipeline dans un répertoire temporaire isolé, puis publie le
manifest et le résultat de la demande dans Blob. Aucun déclencheur quotidien n'est activé.

```bash
uv sync
uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt --output-file requirements.txt
az login
uv run python -m scripts.deploy_function --app-name func-riftlab-dev-023139 --host-storage striftlabfunc023139
uv run python -m scripts.invoke_function --app-name func-riftlab-dev-023139 --max-matches 3
```

Le script de déploiement crée un stockage interne distinct, la Function App et sa
supervision, puis attribue à l'identité managée le rôle `Storage Blob Data Contributor`
sur le seul conteneur RAW. Il transfère les variables Riot depuis `.env` vers les
paramètres Azure sans les afficher. Renouveler une clé Riot impose de retransférer
ce paramètre vers Azure ; modifier uniquement `.env` ne met pas l'application à jour.
Les connexions du runtime Functions et de la queue sont gérées séparément par
`AzureWebJobsStorage` ; le code métier utilise l'identité managée pour Blob.

Le package ZIP est construit par liste explicite de fichiers, sans `.env`, données,
tests ni environnement Python local. Les dépendances sont compilées dans Azure
pour Linux. Les trois fonctions sont dans `function_app.py` :

- `POST /api/ingestion` : corps `{"max_matches": 3}`, entier entre 1 et 50.
- `GET /api/ingestion/{request_id}` : résultat final ou HTTP 202 si en attente/inconnu.
- `ingest_worker` : traitement de la queue `riftlab-ingestion`.

Les deux routes HTTP exigent une clé dans l'en-tête `x-functions-key`. Le script
d'invocation la récupère en mémoire via Azure CLI et vérifie aussi le refus sans clé.
Le résultat final est stocké dans `requests/<request_id>.json` et contient le `run_id`
et le chemin du manifest. Il est préférable de commencer par 3 matchs : le disque
temporaire cloud ne réutilise pas les fichiers du poste local, donc Riot est sollicité
à nouveau, même si les blobs finissent par être ignorés après comparaison.

Une erreur métier produit un résultat `FAILED` ou `PARTIAL_SUCCESS` ; relancer
manuellement après correction. Une erreur technique non récupérée est envoyée
dans `riftlab-ingestion-poison` après une tentative, sans boucle automatique sur
une clé Riot expirée. Un arrêt forcé peut laisser une demande sans résultat : consulter
les logs et la queue poison. La concurrence est limitée par instance ; lancer un seul
lot à la fois pour respecter le quota Riot partagé. Ne pas augmenter le volume
ou multiplier les lancements avant d'avoir défini une limite de débit partagée.
