# Dragon Brain

[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Русский](README.ru.md) | [한국어](README.ko.md) | [Português](README.pt-BR.md) | [Deutsch](README.de.md) | [Français](README.fr.md)

**Persistente Speicherinfrastruktur für KI-Agenten.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)
[![MCP-Werkzeuge](https://img.shields.io/badge/MCP%20tools-34-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-1%2C166%20passing-brightgreen)]()
[![Qualität](https://img.shields.io/badge/gauntlet-A%E2%88%92%20(95%2F100)-blue)]()
[![GPU](https://img.shields.io/badge/GPU-CUDA%20supported-orange.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/iikarus/Dragon-Brain)](https://github.com/iikarus/Dragon-Brain/stargazers)

> **1.599 Erinnerungen** · **34 MCP-Werkzeuge** · **Wissensgraph + Vektorsuche Hybrid** · **Suche <200ms** · **1.166 Tests**

Ein Open-Source MCP-Server, der jedem LLM Langzeitgedächtnis durch einen Wissensgraph + Vektorsuche Hybrid bietet. Speichern Sie Entitäten, Beobachtungen und Beziehungen — und rufen Sie sie semantisch über Sitzungen hinweg ab. Kompatibel mit jedem MCP-Client: Claude Code, Claude Desktop, Cursor, Windsurf, Cline, Gemini CLI.

Im Gegensatz zu flachem Chat-Verlauf oder einfachem RAG versteht Dragon Brain die *Beziehungen* zwischen Erinnerungen — nicht nur Ähnlichkeit. Ein autonomer Agent („Der Bibliothekar") clustert und synthetisiert periodisch Erinnerungen zu übergeordneten Konzepten.

## Schnellstart

> **Voraussetzungen:** [Docker](https://docs.docker.com/get-docker/) und [Docker Compose](https://docs.docker.com/compose/install/).
> **Detaillierte Einrichtung:** Siehe [docs/SETUP.md](docs/SETUP.md) für plattformspezifische Hinweise und Fehlerbehebung.

### 1. Dienste starten

```bash
docker compose up -d
```

Startet 4 Container:
- **FalkorDB** (Wissensgraph) — Port 6379
- **Qdrant** (Vektorsuche) — Port 6333
- **Embedding API** (BGE-M3, Standard CPU) — Port 8001
- **Dashboard** (Streamlit) — Port 8501

> **GPU-Nutzer:** `docker compose --profile gpu up -d` für NVIDIA CUDA-Beschleunigung.

Alles gesund überprüfen:
```bash
docker ps --filter "name=claude-memory"
```

### Installation über pip

```bash
pip install dragon-brain
```

> **Hinweis:** Dragon Brain benötigt FalkorDB und Qdrant als laufende Docker-Dienste.
> Das pip-Paket installiert den MCP-Server — führen Sie zuerst `docker compose up -d` für die Infrastruktur aus.
> Das Embedding-Modell (~1GB) wird über Docker bereitgestellt, kein lokaler Download nötig.

### 2. KI-Agent verbinden

**Claude Code (empfohlen):**
```bash
claude mcp add dragon-brain -- python -m claude_memory.server
```

<details>
<summary><b>Claude Desktop / Andere MCP-Clients</b></summary>

Zur MCP-Client-Konfiguration hinzufügen:

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

Vollständige Vorlage in `mcp_config.example.json`.

</details>

### 3. Erinnern starten

```
Sie: "Merke dir, dass ich Atlas in Rust baue und funktionale Muster bevorzuge."
KI:  [erstellt Entität "Atlas", fügt Beobachtungen zu Rust und funktionalen Mustern hinzu]

Sie (nächste Sitzung): "Was weißt du über meine Projekte?"
KI:  "Sie bauen Atlas in Rust mit funktionalem Ansatz..." [aus dem Graph abgerufen]
```

## Qualität

Produktionsqualitäts-Tests: **1.166 Tests** · Mutationstests (3-evil/1-sad/1-happy) · Eigenschaftsbasierte Tests (38 Hypothesis-Eigenschaften) · Fuzz-Tests (30K+ Eingaben, 0 Abstürze) · Statische Analyse (mypy Strict-Modus, ruff) · Sicherheitsaudit · **Gauntlet-Bewertung: A- (95/100)**.

Vollständige Ergebnisse: [GAUNTLET_RESULTS.md](docs/GAUNTLET_RESULTS.md)

## Anwendungsfälle

- **Langzeitprojekte** — Kontext über Wochen/Monate aufbauen. Dragon Brain merkt sich Architekturentscheidungen, Durchbrüche und die Begründungen.
- **Forschung** — Erstellen Sie einen persistenten Wissensgraph aus Papieren, Konzepten und Verbindungen.
- **Multi-Agenten-Systeme** — Geteilte Speicherschicht für Agententeams. Entdeckungen eines Agenten sind sofort von anderen durchsuchbar.
- **Persönliches Wissensmanagement** — Ihre KI lernt mit der Zeit Ihre Präferenzen, Ihren Arbeitsstil und Ihre Fachexpertise.

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| MCP-Werkzeuge werden nicht angezeigt | MCP-Fehler sind **lautlos**. Prüfen Sie `docker ps --filter "name=claude-memory"` — alle 4 Container müssen gesund sein. |
| `search_memory` gibt leer zurück | Stellen Sie sicher, dass der Embedding-Dienst auf Port 8001 läuft. Testen Sie `curl http://localhost:8001/health`. |
| Verwirrung beim Graph-Namen | Der FalkorDB-Graph heißt `claude_memory` (nicht `dragon_brain`). Verwenden Sie diesen Namen für direkte Cypher-Abfragen. |

Mehr: [docs/GOTCHAS.md](docs/GOTCHAS.md) · [docs/RUNBOOK.md](docs/RUNBOOK.md)

## Lizenz

[MIT](LICENSE)
