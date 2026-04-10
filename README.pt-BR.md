# Dragon Brain

[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Русский](README.ru.md) | [한국어](README.ko.md) | [Português](README.pt-BR.md) | [Deutsch](README.de.md) | [Français](README.fr.md)

**Infraestrutura de memória persistente para agentes de IA.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)
[![Ferramentas MCP](https://img.shields.io/badge/MCP%20tools-34-green.svg)]()
[![Testes](https://img.shields.io/badge/tests-1%2C166%20passing-brightgreen)]()
[![Qualidade](https://img.shields.io/badge/gauntlet-A%E2%88%92%20(95%2F100)-blue)]()
[![GPU](https://img.shields.io/badge/GPU-CUDA%20supported-orange.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/iikarus/Dragon-Brain)](https://github.com/iikarus/Dragon-Brain/stargazers)

> **1.599 memórias** · **34 ferramentas MCP** · **Grafo de conhecimento + busca vetorial híbrida** · **busca <200ms** · **1.166 testes**

Um servidor MCP de código aberto que fornece memória de longo prazo a qualquer LLM usando um grafo de conhecimento + busca vetorial híbrida. Armazene entidades, observações e relacionamentos — depois recupere-os semanticamente entre sessões. Funciona com qualquer cliente MCP: Claude Code, Claude Desktop, Cursor, Windsurf, Cline, Gemini CLI.

Diferente do histórico de chat simples ou RAG básico, o Dragon Brain entende as *relações* entre memórias — não apenas similaridade. Um agente autônomo ("O Bibliotecário") periodicamente agrupa e sintetiza memórias em conceitos de ordem superior.

## Início Rápido

> **Pré-requisitos:** [Docker](https://docs.docker.com/get-docker/) e [Docker Compose](https://docs.docker.com/compose/install/).
> **Configuração detalhada:** Veja [docs/SETUP.md](docs/SETUP.md) para notas específicas por plataforma e solução de problemas.

### 1. Iniciar os Serviços

```bash
docker compose up -d
```

Inicia 4 contêineres:
- **FalkorDB** (grafo de conhecimento) — porta 6379
- **Qdrant** (busca vetorial) — porta 6333
- **Embedding API** (BGE-M3, CPU padrão) — porta 8001
- **Dashboard** (Streamlit) — porta 8501

> **Usuários GPU:** `docker compose --profile gpu up -d` para aceleração NVIDIA CUDA.

Verifique se tudo está saudável:
```bash
docker ps --filter "name=claude-memory"
```

### Instalar via pip

```bash
pip install dragon-brain
```

> **Nota:** Dragon Brain requer FalkorDB e Qdrant rodando como serviços Docker.
> O pacote pip instala o servidor MCP — execute `docker compose up -d` primeiro para a infraestrutura.
> O modelo de embedding (~1GB) é servido via Docker, sem download local.

### 2. Conectar seu Agente de IA

**Claude Code (recomendado):**
```bash
claude mcp add dragon-brain -- python -m claude_memory.server
```

<details>
<summary><b>Claude Desktop / Outros Clientes MCP</b></summary>

Adicione à configuração do seu cliente MCP:

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

Template completo em `mcp_config.example.json`.

</details>

### 3. Comece a Lembrar

```
Você: "Lembre que estou construindo o Atlas em Rust e prefiro padrões funcionais."
IA:   [cria entidade "Atlas", adiciona observações sobre Rust e padrões funcionais]

Você (próxima sessão): "O que você sabe sobre meus projetos?"
IA:   "Você está construindo Atlas em Rust com abordagem funcional..." [recuperado do grafo]
```

## Qualidade

Testes de nível produção: **1.166 testes** · testes de mutação (3-evil/1-sad/1-happy) · testes baseados em propriedades (38 propriedades Hypothesis) · fuzz testing (30K+ entradas, 0 crashes) · análise estática (mypy modo estrito, ruff) · auditoria de segurança · **Pontuação Gauntlet: A- (95/100)**.

Resultados completos: [GAUNTLET_RESULTS.md](docs/GAUNTLET_RESULTS.md)

## Casos de Uso

- **Projetos de longo prazo** — Acumule contexto por semanas/meses. Dragon Brain lembra decisões de arquitetura, avanços e o raciocínio por trás deles.
- **Pesquisa** — Crie um grafo de conhecimento persistente de artigos, conceitos e conexões.
- **Sistemas multi-agente** — Camada de memória compartilhada para equipes de agentes. Descobertas de um agente são imediatamente pesquisáveis por outros.
- **Gestão de conhecimento pessoal** — Sua IA aprende suas preferências, estilo de trabalho e expertise ao longo do tempo.

## Solução de Problemas

| Problema | Solução |
|----------|---------|
| Ferramentas MCP não aparecem | Falhas MCP são **silenciosas**. Verifique `docker ps --filter "name=claude-memory"` — todos os 4 contêineres devem estar saudáveis. |
| `search_memory` retorna vazio | Verifique se o serviço de embedding está rodando na porta 8001. Teste `curl http://localhost:8001/health`. |
| Confusão com nome do grafo | O grafo FalkorDB se chama `claude_memory` (não `dragon_brain`). Use esse nome para consultas Cypher diretas. |

Mais: [docs/GOTCHAS.md](docs/GOTCHAS.md) · [docs/RUNBOOK.md](docs/RUNBOOK.md)

## Licença

[MIT](LICENSE)
