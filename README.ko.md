# Dragon Brain

[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Русский](README.ru.md) | [한국어](README.ko.md) | [Português](README.pt-BR.md) | [Deutsch](README.de.md) | [Français](README.fr.md)

**AI 에이전트를 위한 영구 메모리 인프라.**

[![LongMemEval](https://img.shields.io/badge/LongMemEval_R%405-100%25-gold?style=for-the-badge)](benchmarks/longmemeval/RESULTS.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)
[![MCP 도구](https://img.shields.io/badge/MCP%20tools-34-green.svg)]()
[![테스트](https://img.shields.io/badge/tests-1%2C281%20passing-brightgreen)]()
[![품질](https://img.shields.io/badge/gauntlet-A%E2%88%92%20(95%2F100)-blue)]()
[![GPU](https://img.shields.io/badge/GPU-CUDA%20supported-orange.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/iikarus/Dragon-Brain)](https://github.com/iikarus/Dragon-Brain/stargazers)

> **LongMemEval R@5 100%** · **1,599 메모리** · **34 MCP 도구** · **그래프 + 벡터 하이브리드** · **200ms 미만 검색** · **LLM 불필요**

지식 그래프 + 벡터 검색 하이브리드를 통해 모든 LLM에 장기 기억을 제공하는 오픈소스 MCP 서버입니다. 엔티티, 관찰, 관계를 저장하고 세션 간에 시맨틱하게 검색합니다. 모든 MCP 클라이언트와 호환: Claude Code, Claude Desktop, Cursor, Windsurf, Cline, Gemini CLI.

플랫 채팅 기록이나 단순 RAG와 달리, Dragon Brain은 기억 간의 *관계*를 이해합니다 — 유사성만이 아닙니다. 자율 에이전트("사서")가 주기적으로 기억을 클러스터링하고 상위 개념으로 합성합니다.

## 빠른 시작

> **필수 조건:** [Docker](https://docs.docker.com/get-docker/) 및 [Docker Compose](https://docs.docker.com/compose/install/).
> **상세 설정:** 플랫폼별 참고사항과 문제 해결은 [docs/SETUP.md](docs/SETUP.md) 참조.

### 1. 서비스 시작

```bash
docker compose up -d
```

4개의 컨테이너가 시작됩니다:
- **FalkorDB** (지식 그래프) — 포트 6379
- **Qdrant** (벡터 검색) — 포트 6333
- **Embedding API** (BGE-M3, 기본 CPU) — 포트 8001
- **Dashboard** (Streamlit) — 포트 8501

> **GPU 사용자:** NVIDIA CUDA 가속을 위해 `docker compose --profile gpu up -d` 사용.

모든 서비스가 정상인지 확인:
```bash
docker ps --filter "name=claude-memory"
```

### pip으로 설치

```bash
pip install dragon-brain
```

> **참고:** Dragon Brain은 Docker 서비스로 실행 중인 FalkorDB와 Qdrant가 필요합니다.
> pip 패키지는 MCP 서버를 설치합니다 — 인프라를 위해 먼저 `docker compose up -d`를 실행하세요.
> 임베딩 모델(~1GB)은 Docker를 통해 제공되며, 로컬 다운로드는 필요 없습니다.

### 2. AI 에이전트 연결

**Claude Code (권장):**
```bash
claude mcp add dragon-brain -- python -m claude_memory.server
```

<details>
<summary><b>Claude Desktop / 기타 MCP 클라이언트</b></summary>

MCP 클라이언트 설정에 추가:

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

전체 템플릿은 `mcp_config.example.json` 참조.

</details>

### 3. 기억 시작

```
당신: "Rust로 Atlas 프로젝트를 만들고 있고 함수형 패턴을 선호한다고 기억해줘."
AI:   [엔티티 "Atlas" 생성, Rust와 함수형 패턴에 대한 관찰 추가]

당신 (다음 세션): "내 프로젝트에 대해 뭘 알고 있어?"
AI:   "Atlas를 Rust로 함수형 접근 방식으로 구축 중입니다..." [그래프에서 검색]
```

## 비교

| 기능 | 채팅 기록 | 단순 RAG | Dragon Brain |
|------|:--------:|:--------:|:------------:|
| 세션 간 유지 | 아니오 | 상황에 따라 | **예** |
| 관계 이해 | 아니오 | 아니오 | **예 (그래프)** |
| 시맨틱 검색 | 아니오 | 예 | **예 (하이브리드)** |
| 시간 여행 쿼리 | 아니오 | 아니오 | **예** |
| 자동 클러스터링 | 아니오 | 아니오 | **예 (사서)** |
| 관계 발견 | 아니오 | 아니오 | **예 (시맨틱 레이더)** |
| 모든 MCP 클라이언트 지원 | 해당 없음 | 다양 | **예** |

## 품질

프로덕션 수준 테스트: **1,166개 테스트** · 뮤테이션 테스트 (3-evil/1-sad/1-happy) · 속성 기반 테스트 (38개 Hypothesis 속성) · 퍼즈 테스트 (30K+ 입력, 크래시 0) · 정적 분석 (mypy strict, ruff) · 보안 감사 · **Gauntlet 점수: A- (95/100)**.

전체 결과: [GAUNTLET_RESULTS.md](docs/GAUNTLET_RESULTS.md)

## 사용 사례

- **장기 프로젝트** — 수주/수개월에 걸쳐 컨텍스트를 축적. Dragon Brain이 아키텍처 결정, 돌파구, 근거를 기억합니다.
- **연구** — 논문, 개념, 연결의 영구적 지식 그래프 생성. 시맨틱 검색이 키워드가 아닌 의미로 관련 기억을 찾습니다.
- **멀티 에이전트 시스템** — 에이전트 팀을 위한 공유 메모리 레이어. 한 에이전트의 발견을 즉시 다른 에이전트가 검색 가능.
- **개인 지식 관리** — AI가 시간이 지남에 따라 당신의 선호, 작업 스타일, 도메인 전문 지식을 학습.

## 문제 해결

| 문제 | 해결 |
|------|------|
| MCP 도구가 표시되지 않음 | MCP 실패는 **조용합니다**. `docker ps --filter "name=claude-memory"` 확인 — 4개 컨테이너 모두 정상이어야 합니다. |
| `search_memory`가 빈 결과 반환 | 임베딩 서비스가 포트 8001에서 실행 중인지 확인. `curl http://localhost:8001/health`로 검증. |
| 그래프 이름 혼동 | FalkorDB 그래프 이름은 `claude_memory`입니다 (`dragon_brain` 아님). 직접 Cypher 쿼리 시 이 이름을 사용하세요. |

자세한 내용: [docs/GOTCHAS.md](docs/GOTCHAS.md) · [docs/RUNBOOK.md](docs/RUNBOOK.md)

## 라이선스

[MIT](LICENSE)
