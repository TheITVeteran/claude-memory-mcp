# Dragon Brain

[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Русский](README.ru.md) | [한국어](README.ko.md) | [Português](README.pt-BR.md) | [Deutsch](README.de.md) | [Français](README.fr.md)

**Infrastructure de mémoire persistante pour les agents IA.**

[![LongMemEval](https://img.shields.io/badge/LongMemEval_R%405-100%25-gold?style=for-the-badge)](benchmarks/longmemeval/RESULTS.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)
[![Outils MCP](https://img.shields.io/badge/MCP%20tools-34-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-1%2C281%20passing-brightgreen)]()
[![Qualité](https://img.shields.io/badge/gauntlet-A%E2%88%92%20(95%2F100)-blue)]()
[![GPU](https://img.shields.io/badge/GPU-CUDA%20supported-orange.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/iikarus/Dragon-Brain)](https://github.com/iikarus/Dragon-Brain/stargazers)

> **LongMemEval R@5 100%** · **1 599 mémoires** · **34 outils MCP** · **Graphe + Vecteur hybride** · **recherche <200ms** · **Aucun LLM requis**

Un serveur MCP open source qui fournit une mémoire à long terme à n'importe quel LLM grâce à un hybride graphe de connaissances + recherche vectorielle. Stockez des entités, des observations et des relations — puis retrouvez-les sémantiquement entre les sessions. Compatible avec tout client MCP : Claude Code, Claude Desktop, Cursor, Windsurf, Cline, Gemini CLI.

Contrairement à l'historique de chat simple ou au RAG basique, Dragon Brain comprend les *relations* entre les souvenirs — pas seulement la similarité. Un agent autonome (« Le Bibliothécaire ») regroupe périodiquement les souvenirs et les synthétise en concepts d'ordre supérieur.

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

## Qualité

Tests de niveau production : **1 281 tests** · tests de mutation (3-evil/1-sad/1-happy) · tests basés sur les propriétés (38 propriétés Hypothesis) · fuzz testing (30K+ entrées, 0 crash) · analyse statique (mypy mode strict, ruff) · audit de sécurité · **Score Gauntlet : A- (95/100)**.

Résultats complets : [GAUNTLET_RESULTS.md](docs/GAUNTLET_RESULTS.md)

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
