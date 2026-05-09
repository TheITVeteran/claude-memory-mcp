# Dragon Brain

[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Русский](README.ru.md) | [한국어](README.ko.md) | [Português](README.pt-BR.md) | [Deutsch](README.de.md) | [Français](README.fr.md)

**Speicherinfrastruktur für KI-Agenten — by design mit Fail-Loud-Architektur.**

[![LongMemEval](https://img.shields.io/badge/LongMemEval_R%405-100%25-gold?style=for-the-badge)](benchmarks/longmemeval/RESULTS.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)
[![MCP-Werkzeuge](https://img.shields.io/badge/MCP%20tools-34-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-1%2C281%20passing-brightgreen)]()
[![Qualität](https://img.shields.io/badge/gauntlet-A%E2%88%92%20(95%2F100)-blue)]()
[![GPU](https://img.shields.io/badge/GPU-CUDA%20supported-orange.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/iikarus/Dragon-Brain)](https://github.com/iikarus/Dragon-Brain/stargazers)

> **LongMemEval R@5 100%** · **34 MCP-Tools** · **Sub-200ms Hybrid-Suche** · **CI-geprüfte Fail-Loud-Verträge** · **Kein LLM erforderlich**

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

## Im Audit geschmiedet (Forged in Audit)

Die meisten Open-Source-Speichersysteme polieren nur den "Happy Path". Hier ist der Bug, den Dragon Brain zwei Monate lang in Produktion ausgeliefert hat – und die Infrastruktur, die nun existiert, damit er nicht zurückkehren kann.

### Die Lüge (The lie)

Vor April 2026 sah die `search()`-Pipeline in etwa so aus:

```python
try:
    # ... 6-Kanal-Retrieval-Pipeline ...
except Exception:
    return []
```

Das MCP-Tool `search_memory` wandelte dann `[]` in den String `"No results found."` um. Claude erhielt diesen String und behandelte ihn als maßgeblich – *"der Benutzer hat wirklich keine Erinnerungen zu diesem Thema"* – wenn in Wirklichkeit der Embedding-Dienst abgestürzt war, FalkorDB unerreichbar war oder Qdrant ein Timeout hatte.

**Jede degradierte Abfrage bedeutete, dass die KI ohne ihr Wissen mit fehlendem Kontext argumentierte.** Eine selbstbewusste Lüge, die nicht von echter Leere zu unterscheiden war, hartkodiert in die am häufigsten aufgerufene Funktion des Systems.

### Der Fix (The fix)

Ein 4-stufiges adversariales Audit fand **83 Vertragsverletzungen in 37 Quelldateien**. Zehn Batches von Korrekturen wurden zwischen April und Mai 2026 ausgeliefert:

- Infrastrukturausfälle lösen jetzt einen **`SearchError`** aus – eine leere Liste bedeutet jetzt *nur noch* "keine Ergebnisse gefunden".
- **MCP `search_memory`** gibt den strukturierten Fehler `{"error": "MEMORY_LAYER_DEGRADED", "retry_safe": true}` zurück – dies signalisiert der KI ausdrücklich eine Degradierung, anstatt eine selbstbewusste Lüge aufzutischen.
- **Cross-Store-Kompensation** bei Erstellung/Aktualisierung/Löschung von Entitäten – wenn ein Qdrant-Schreibvorgang fehlschlägt, wird FalkorDB zurückgerollt, um Split-Brain-Waisen zu verhindern.
- **Das Schreiben von Edges verwendet `MERGE`, nicht `CREATE`** – wiederholte Aufrufe von `create_relationship` duplizieren keine Kanten.
- **Fehlgeschlagene FTS-Schreibvorgänge propagieren** zum Aufrufer – stille Indexveralterung wurde eliminiert.
- **Der Lock-Manager löst bei Konflikten `TimeoutError` aus** – er fährt niemals stillschweigend fort, ohne den Lock zu erhalten.
- **MCP-Tools haben semantische Validierung** – fehlerhafte UUIDs geben `{"error": "ENTITY_NOT_FOUND"}` zurück, anstatt stillschweigend leere Ergebnisse zu liefern.

### Die Disziplin (The discipline)

- **`tox -e contracts`** — Das CI-Gate ist bei einer Baseline von **13 Verstößen** (von 64 gesunken) gesperrt. Neue Verstöße lassen den Build vor dem Merge fehlschlagen. Vierteljährliche Überprüfungen werden diese Baseline kontinuierlich in Richtung Null drücken.
- **Verhaltensbasierte Integrationstests** — `testcontainers-python` startet reale `falkordb/falkordb:v4.14.11` und `qdrant/qdrant:v1.16.3` und führt dann mitten im Vorgang `container.kill()` aus, um sicherzustellen, dass der Fail-Loud-Vertrag durchgehend Bestand hat.
- **Natives asynchrones Repository** — `AsyncMemoryRepository` isoliert synchrone Datenbanktreiber in Thread-Pools an ca. 75 Aufrufstellen.
- **Trust-Boundary-Dokumentation** — Jede prozessübergreifende Grenze hat einen ausdrücklichen Vertrag, der in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) aufgezeichnet ist.

### Warum das wichtig ist

Wenn Ihre Speicherschicht über ihre eigenen Ausfallmodi lügen kann, wird jeder nachgeschaltete Argumentationsschritt korrumpiert. KI-Agenten vertrauen ihren Werkzeugen. Werkzeuge, die selbstbewusst leere Ergebnisse fabrizieren, vergiften ganze Argumentationsketten.

Soweit wir wissen, ist Dragon Brain das erste Open-Source-Speichersystem, das Fail-Loud-Verhalten als CI-erzwungenen Vertrag behandelt. Wenn dies jemals wieder vorkommt, schlägt der Build fehl, bevor der Code überhaupt gemergt wird.

### Belege (Receipts)

- **1.337 Tests** in 106 Testdateien, 0 Fehlschläge, 0 übersprungen
- **Mutationstests** — 2.270 Mutanten, 1.184 getötet in 27 Quelldateien (3-evil/1-sad/1-happy pro Funktion)
- **Property-based Tests** — 38 Hypothesis-Eigenschaften
- **Fuzz-Tests** — 30.000+ Eingaben, 0 Abstürze
- **Statische Analyse** — mypy strict mode (0 Fehler), ruff (0 Fehler)
- **Sicherheitsaudit** — Cypher-Injection-Audit, Credential-Scanning
- **Dead-Code-Erkennung** — Vulture (0 Funde)
- **Dragon Brain Gauntlet** — 20 Runden automatisierte Qualitätsprüfung, **A− (95/100)**

Vollständige Gauntlet-Ergebnisse: [docs/GAUNTLET_RESULTS.md](docs/GAUNTLET_RESULTS.md) · Trust Boundaries: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Integrationstests: [tests/integration/test_db_kill_scenarios.py](tests/integration/test_db_kill_scenarios.py)

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
