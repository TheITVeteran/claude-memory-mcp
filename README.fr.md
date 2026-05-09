# Dragon Brain

[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Русский](README.ru.md) | [한국어](README.ko.md) | [Português](README.pt-BR.md) | [Deutsch](README.de.md) | [Français](README.fr.md)

**Infrastructure de mémoire pour les agents IA — qui signale bruyamment ses échecs (fail-loud), par conception.**

[![LongMemEval](https://img.shields.io/badge/LongMemEval_R%405-100%25-gold?style=for-the-badge)](benchmarks/longmemeval/RESULTS.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)
[![Outils MCP](https://img.shields.io/badge/MCP%20tools-34-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-1%2C281%20passing-brightgreen)]()
[![Qualité](https://img.shields.io/badge/gauntlet-A%E2%88%92%20(95%2F100)-blue)]()
[![GPU](https://img.shields.io/badge/GPU-CUDA%20supported-orange.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/iikarus/Dragon-Brain)](https://github.com/iikarus/Dragon-Brain/stargazers)

> **LongMemEval R@5 100%** · **34 outils MCP** · **Recherche hybride sub-200ms** · **Contrats fail-loud imposés par l'IC** · **Pas de LLM requis**

Un serveur MCP open source qui fournit une mémoire à long terme à n'importe quel LLM grâce à un hybride graphe de connaissances + recherche vectorielle. Stockez des entités, des observations et des relations — puis retrouvez-les sémantiquement entre les sessions. Compatible avec tout client MCP : Claude Code, Claude Desktop, Cursor, Windsurf, Cline, Gemini CLI.

Contrairement à l'historique de chat simple ou au RAG basique, Dragon Brain comprend les *relations* entre les souvenirs — pas seulement la similarité. Un agent autonome (« Le Bibliothécaire ») regroupe périodiquement les souvenirs et les synthétise en concepts d'ordre supérieur.

**Et il vous dit quand il ne peut pas s'en souvenir — au lieu de prétendre que la mémoire n'a jamais été là.**

## Démarrage Rapide

> **Prérequis :** [Docker](https://docs.docker.com/get-docker/) et [Docker Compose](https://docs.docker.com/compose/install/).
> **Configuration détaillée :** Voir [docs/SETUP.md](docs/SETUP.md) pour les notes spécifiques à chaque plateforme et le dépannage.

### 1. Démarrer les Services

```bash
docker compose up -d
```

Lance 4 conteneurs :
- **FalkorDB** (graphe de connaissances) — port 6379
- **Qdrant** (recherche vectorielle) — port 6333
- **Embedding API** (BGE-M3, CPU par défaut) — port 8001
- **Dashboard** (Streamlit) — port 8501

> **Utilisateurs GPU :** `docker compose --profile gpu up -d` pour l'accélération NVIDIA CUDA.

Vérifier que tout est sain :
```bash
docker ps --filter "name=claude-memory"
```

### Installation via pip

```bash
pip install dragon-brain
```

> **Note :** Dragon Brain nécessite FalkorDB et Qdrant en tant que services Docker.
> Le paquet pip installe le serveur MCP — lancez d'abord `docker compose up -d` pour l'infrastructure.
> Le modèle d'embedding (~1 Go) est servi via Docker, pas de téléchargement local nécessaire.

### 2. Connecter votre Agent IA

**Claude Code (recommandé) :**
```bash
claude mcp add dragon-brain -- python -m claude_memory.server
```

<details>
<summary><b>Claude Desktop / Autres Clients MCP</b></summary>

Ajouter à la configuration de votre client MCP :

```json
{
  "mcpServers": {
    "dragon-brain": {
      "command": "python",
      "args": ["-m", "claude_memory.server"],
      "env": {
        "FALKORDB_HOST": "localhost",
        "FALKORDB_PORT": "6379",
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "6333",
        "EMBEDDING_API_URL": "http://localhost:8001"
      }
    }
  }
}
```

Modèle complet dans `mcp_config.example.json`.

</details>

### 3. Commencez à Mémoriser

```
Vous : "Retiens que je construis Atlas en Rust et que je préfère les patterns fonctionnels."
IA :   [crée l'entité "Atlas", ajoute des observations sur Rust et les patterns fonctionnels]

Vous (session suivante) : "Que sais-tu de mes projets ?"
IA :   "Vous construisez Atlas en Rust avec une approche fonctionnelle..." [rappelé du graphe]
```

## Forgé dans l'Audit (Forged in Audit)

La plupart des systèmes de mémoire open source polissent le « chemin heureux » (happy path). Voici le bug que Dragon Brain a envoyé en production pendant deux mois — et l'infrastructure qui existe maintenant pour qu'il ne puisse plus jamais revenir.

### Le mensonge (The lie)

Avant avril 2026, le pipeline de récupération `search()` ressemblait à ceci :

```python
try:
    # ... pipeline de récupération à 6 canaux ...
except Exception:
    return []
```

L'outil `search_memory` de MCP transformait ensuite `[]` en la chaîne `"No results found."`. Claude recevait cette chaîne et la considérait comme une vérité absolue — *« l'utilisateur n'a vraiment aucun souvenir sur ce sujet »* — alors qu'en réalité le service d'embeddings avait planté, FalkorDB était injoignable, ou Qdrant avait expiré (timeout).

**Chaque requête dégradée était l'IA raisonnant avec un contexte manquant sans le savoir.** Un mensonge confiant indiscernable d'un vide authentique, codé en dur dans la fonction la plus appelée du système.

### La correction (The fix)

Un audit contradictoire en 4 phases a révélé **83 violations de contrat réparties dans 37 fichiers source**. Dix lots de correctifs ont été expédiés entre avril et mai 2026 :

- Une panne d'infrastructure déclenche maintenant une **`SearchError`** — une liste vide signifie *uniquement* « aucun résultat trouvé ».
- **MCP `search_memory`** renvoie une erreur structurée `{"error": "MEMORY_LAYER_DEGRADED", "retry_safe": true}` — signalant explicitement la dégradation à l'IA, jamais un mensonge confiant.
- **Compensation inter-stockage** lors de la création/mise à jour/suppression d'entités — un échec d'écriture dans Qdrant annule les modifications dans FalkorDB pour éviter les orphelins (split-brain).
- **L'écriture des arêtes utilise `MERGE`, pas `CREATE`** — les appels `create_relationship` réessayés ne dupliquent pas les arêtes.
- **Les échecs d'écriture FTS se propagent** à l'appelant — le vieillissement silencieux de l'index a été éliminé.
- **Le gestionnaire de verrous lève `TimeoutError`** en cas de contention — il ne procède jamais silencieusement sans obtenir le verrou.
- **Les outils MCP ont une validation sémantique** — de mauvais UUID renvoient `{"error": "ENTITY_NOT_FOUND"}` et non des résultats vides silencieux.

### La discipline (The discipline)

- **`tox -e contracts`** — La barrière d'Intégration Continue (IC) est fixée à un seuil de **13 violations** (contre 64 auparavant). De nouvelles violations feront échouer le build avant la fusion (merge). Des révisions trimestrielles forceront ce seuil vers zéro.
- **Tests d'intégration comportementale** — `testcontainers-python` démarre de véritables conteneurs `falkordb/falkordb:v4.14.11` et `qdrant/qdrant:v1.16.3`, puis exécute `container.kill()` au milieu d'une opération pour s'assurer que le contrat *fail-loud* (signaler bruyamment l'échec) est maintenu de bout en bout.
- **Dépôt asynchrone natif** — `AsyncMemoryRepository` isole les pilotes de bases de données synchrones dans des pools de threads sur environ 75 sites d'appel.
- **Documentation des limites de confiance** — chaque limite inter-processus possède un contrat explicite enregistré dans [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Pourquoi c'est important

Si votre couche de mémoire peut mentir sur ses propres défaillances, chaque étape de raisonnement en aval est corrompue. Les agents IA font confiance à leurs outils. Les outils qui fabriquent avec confiance des résultats vides empoisonnent des chaînes de raisonnement entières.

À notre connaissance, Dragon Brain est le premier système de mémoire open source à traiter le comportement *fail-loud* comme un contrat imposé par l'IC. Si cela se reproduit, la construction échouera avant même de fusionner.

### Reçus (Receipts)

- **1 337 tests** sur 106 fichiers de test, 0 échec, 0 ignoré
- **Tests de mutation** — 2 270 mutants, 1 184 tués dans 27 fichiers source (3-evil/1-sad/1-happy par fonction)
- **Tests basés sur les propriétés** — 38 propriétés Hypothesis
- **Fuzzing** — plus de 30 000 entrées, 0 plantage
- **Analyse statique** — mode strict de mypy (0 erreur), ruff (0 erreur)
- **Audit de sécurité** — Audit d'injection Cypher, scan d'identifiants
- **Détection de code mort** — Vulture (0 trouvaille)
- **Dragon Brain Gauntlet** — 20 cycles d'audit qualité automatisé, **A− (95/100)**

Résultats complets du Gauntlet : [docs/GAUNTLET_RESULTS.md](docs/GAUNTLET_RESULTS.md) · Limites de confiance : [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Tests d'intégration : [tests/integration/test_db_kill_scenarios.py](tests/integration/test_db_kill_scenarios.py)

## Cas d'Utilisation

- **Projets long terme** — Accumulez du contexte sur des semaines/mois. Dragon Brain retient les décisions d'architecture, les percées et le raisonnement.
- **Recherche** — Créez un graphe de connaissances persistant d'articles, concepts et connexions.
- **Systèmes multi-agents** — Couche de mémoire partagée pour les équipes d'agents. Les découvertes d'un agent sont immédiatement recherchables par les autres.
- **Gestion des connaissances personnelles** — Votre IA apprend vos préférences, votre style de travail et votre expertise au fil du temps.

## Dépannage

| Problème | Solution |
|----------|----------|
| Les outils MCP n'apparaissent pas | Les échecs MCP sont **silencieux**. Vérifiez `docker ps --filter "name=claude-memory"` — les 4 conteneurs doivent être sains. |
| `search_memory` renvoie vide | Vérifiez que le service d'embedding tourne sur le port 8001. Testez `curl http://localhost:8001/health`. |
| Confusion sur le nom du graphe | Le graphe FalkorDB s'appelle `claude_memory` (pas `dragon_brain`). Utilisez ce nom pour les requêtes Cypher directes. |

Plus : [docs/GOTCHAS.md](docs/GOTCHAS.md) · [docs/RUNBOOK.md](docs/RUNBOOK.md)

## Licence

[MIT](LICENSE)
