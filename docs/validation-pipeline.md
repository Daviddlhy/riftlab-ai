# Pipeline traçable — validation du 22 octobre 2026

## Exécutions réelles

Le rejeu local vers Azure a terminé en `SUCCESS` :

- Run : `20261022T070404Z-fc04d2c4d43a42c48f12c49d7ede3e68`.
- 50 IDs, 50 matchs et 50 timelines réutilisés localement.
- Azure : 0 payload créé, 100 blobs identiques vérifiés puis ignorés, 0 échec.
- Manifest final publié puis relu dans
  `manifests/run_id=20261022T070404Z-fc04d2c4d43a42c48f12c49d7ede3e68/manifest.json`.
- Copie locale :
  `data/manifests/20261022T070404Z-fc04d2c4d43a42c48f12c49d7ede3e68/manifest.json`.

Un essai avec découverte Riot a terminé en `FAILED`, avant tout traitement de match :

- Run : `20261022T070244Z-9696bebe2fce4295acc93fed65713a9a`.
- Réponse Riot HTTP 401 ; aucun retry sur cette erreur d'authentification.
- Échec de découverte et code HTTP enregistrés sans message HTTP ni secret.
- Manifest d'échec publié et relu dans Azure.

Après mise à jour de la clé dans `.env`, le lancement avec découverte Riot a
terminé en `SUCCESS` :

- Run : `20261022T071253Z-65a0b4fd08de459294bc732533479d78`.
- Authentification et découverte Riot réussies : 50 IDs Solo/Duo.
- Les 50 matchs et 50 timelines correspondants étaient déjà présents localement.
- Azure : 100 blobs vérifiés puis ignorés, aucun payload créé, aucun échec.
- Manifest final publié puis relu dans
  `manifests/run_id=20261022T071253Z-65a0b4fd08de459294bc732533479d78/manifest.json`.

Cette exécution valide la découverte réelle Riot suivie du rejeu Azure. Le
téléchargement de nouveaux payloads n'a pas été sollicité : tous les fichiers du
lot étaient déjà valides localement. Ce chemin est couvert par les tests simulés.

## Scénarios automatisés

Les tests utilisent un stockage en mémoire et des réponses Riot simulées :

- Extraction, publication du manifest et relance sans doublon ni nouvel appel de payload.
- Interruption après le premier objet, puis reprise du lot et conservation des données.
- Reprise par CLI depuis le manifest, sans nouvelle découverte du lot.
- Arrêt sur 401, 403 ou 429 épuisé ; opérations restantes explicitement non traitées.
- Retry 429 et 503 avec délai et événement corrélé au run, sans PUUID dans les logs.
- Payload vide refusé avant sauvegarde et upload.
- Blob existant différent préservé et signalé comme échec.
- Découverte ou publication du manifest en échec sans faux résultat de succès local.

Les commandes et limites de reprise sont décrites dans le README. Le checkpoint
local peut rester `RUNNING` après une terminaison forcée ; le manifest distant n'est
publié qu'en fin d'exécution. L'atomicité du checkpoint repose sur le système de
fichiers local, avec une seule exécution active par répertoire de données.
