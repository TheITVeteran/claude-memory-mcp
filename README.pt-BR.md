# Dragon Brain

[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Русский](README.ru.md) | [한국어](README.ko.md) | [Português](README.pt-BR.md) | [Deutsch](README.de.md) | [Français](README.fr.md)

**Infraestrutura de memória para agentes de IA — que falha de forma ruidosa (fail-loud), por design.**

[![LongMemEval](https://img.shields.io/badge/LongMemEval_R%405-100%25-gold?style=for-the-badge)](benchmarks/longmemeval/RESULTS.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)
[![Ferramentas MCP](https://img.shields.io/badge/MCP%20tools-34-green.svg)]()
[![Testes](https://img.shields.io/badge/tests-1%2C281%20passing-brightgreen)]()
[![Qualidade](https://img.shields.io/badge/gauntlet-A%E2%88%92%20(95%2F100)-blue)]()
[![GPU](https://img.shields.io/badge/GPU-CUDA%20supported-orange.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/iikarus/Dragon-Brain)](https://github.com/iikarus/Dragon-Brain/stargazers)

> **LongMemEval R@5 100%** · **34 ferramentas MCP** · **Pesquisa híbrida sub-200ms** · **Contratos fail-loud aplicados via CI** · **Sem necessidade de LLM**

Um servidor MCP de código aberto que fornece memória de longo prazo a qualquer LLM usando um grafo de conhecimento + busca vetorial híbrida. Armazene entidades, observações e relacionamentos — depois recupere-os semanticamente entre sessões. Funciona com qualquer cliente MCP: Claude Code, Claude Desktop, Cursor, Windsurf, Cline, Gemini CLI.

Diferente do histórico de chat simples ou RAG básico, o Dragon Brain entende as *relações* entre memórias — não apenas similaridade. Um agente autônomo ("O Bibliotecário") periodicamente agrupa e sintetiza memórias em conceitos de ordem superior.

**E ele diz a você quando não consegue lembrar — em vez de fingir que a memória nunca esteve lá.**

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

## Forjado na Auditoria (Forged in Audit)

A maioria dos sistemas de memória de código aberto aprimora apenas o "caminho feliz" (happy path). Aqui está o bug que o Dragon Brain enviou para produção por dois meses — e a infraestrutura que agora existe para que ele não possa retornar.

### A mentira (The lie)

Antes de abril de 2026, o pipeline de `search()` parecia mais ou menos assim:

```python
try:
    # ... pipeline de recuperação de 6 canais ...
except Exception:
    return []
```

A ferramenta `search_memory` do MCP então transformava `[]` na string `"No results found."`. O Claude recebia essa string e a tratava como oficial — *"o usuário genuinamente não tem memórias sobre esse tópico"* — quando, na realidade, o serviço de embeddings havia travado, o FalkorDB estava inacessível ou o Qdrant havia expirado (timeout).

**Cada consulta degradada era a IA operando com o contexto ausente sem saber.** Uma mentira confiante indistinguível do vazio genuíno, incorporada à função mais chamada do sistema.

### A correção (The fix)

Uma auditoria adversarial de 4 fases encontrou **83 violações de contrato em 37 arquivos de origem**. Dez lotes de correções foram enviados entre abril e maio de 2026:

- Falhas de infraestrutura agora geram um **`SearchError`** — uma lista vazia significa "nenhum resultado encontrado" e *apenas* isso.
- **O `search_memory` do MCP** retorna o erro estruturado `{"error": "MEMORY_LAYER_DEGRADED", "retry_safe": true}` — sinalizando explicitamente a degradação para a IA, nunca uma mentira confiante.
- **Compensação entre armazenamentos** na criação/atualização/exclusão da entidade — a falha na gravação do Qdrant reverte o FalkorDB para evitar dados órfãos (split-brain).
- **A gravação de bordas (edges) usa `MERGE`, não `CREATE`** — chamadas repetidas de `create_relationship` não duplicam arestas.
- **Falhas de gravação do FTS se propagam** para quem chamou a função — a desatualização silenciosa do índice foi eliminada.
- **O gerenciador de bloqueio levanta `TimeoutError`** na contenção — nunca prossegue silenciosamente sem obter o bloqueio.
- **As ferramentas MCP têm validação semântica** — UUIDs ruins retornam `{"error": "ENTITY_NOT_FOUND"}` e não resultados vazios silenciosos.

### A disciplina (The discipline)

- **`tox -e contracts`** — A barreira de CI está travada em uma linha de base de **13 violações** (caiu de 64). Novas violações farão o build falhar antes do merge. Revisões trimestrais forçarão essa linha de base em direção a zero.
- **Testes de integração comportamental** — `testcontainers-python` inicializa `falkordb/falkordb:v4.14.11` e `qdrant/qdrant:v1.16.3` reais e, no meio de uma operação, executa `container.kill()` para garantir que o contrato *fail-loud* seja mantido de ponta a ponta.
- **Repositório nativo assíncrono** — O `AsyncMemoryRepository` isola drivers de banco de dados síncronos em pools de threads em ~75 locais de chamada.
- **Documentação de limites de confiança** — cada limite entre processos possui um contrato explícito registrado em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Por que isso importa

Se sua camada de memória pode mentir sobre seus modos de falha, todas as etapas de raciocínio a jusante estarão corrompidas. Agentes de IA confiam em suas ferramentas. Ferramentas que fabricam com confiança resultados vazios envenenam cadeias inteiras de raciocínio.

Até onde sabemos, o Dragon Brain é o primeiro sistema de memória de código aberto a tratar o comportamento "fail-loud" como um contrato obrigatório aplicado via CI. Se isso acontecer novamente, o build falhará.

### Recibos (Receipts)

- **1.337 testes** em 106 arquivos de teste, 0 falhas, 0 ignorados
- **Teste de mutação** — 2.270 mutantes, 1.184 eliminados em 27 arquivos de origem (3-evil/1-sad/1-happy por função)
- **Teste baseado em propriedades** — 38 propriedades do Hypothesis
- **Teste de difusão (Fuzz testing)** — mais de 30 mil entradas, 0 travamentos
- **Análise estática** — modo estrito do mypy (0 erros), ruff (0 erros)
- **Auditoria de segurança** — Auditoria de injeção de Cypher, varredura de credenciais
- **Detecção de código inativo** — Vulture (0 descobertas)
- **Dragon Brain Gauntlet** — 20 rodadas de auditoria automatizada de qualidade, **A− (95/100)**

Resultados completos do Gauntlet: [docs/GAUNTLET_RESULTS.md](docs/GAUNTLET_RESULTS.md) · Limites de confiança: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Testes de integração: [tests/integration/test_db_kill_scenarios.py](tests/integration/test_db_kill_scenarios.py)

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
