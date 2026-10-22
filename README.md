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
