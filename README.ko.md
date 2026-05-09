# Dragon Brain

[English](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Русский](README.ru.md) | [한국어](README.ko.md) | [Português](README.pt-BR.md) | [Deutsch](README.de.md) | [Français](README.fr.md)

**AI 에이전트를 위한 기억 인프라 — 의도적으로 큰 소리로 실패(Fail-Loud)하도록 설계되었습니다.**

[![LongMemEval](https://img.shields.io/badge/LongMemEval_R%405-100%25-gold?style=for-the-badge)](benchmarks/longmemeval/RESULTS.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker-compose.yml)
[![MCP 도구](https://img.shields.io/badge/MCP%20tools-34-green.svg)]()
[![테스트](https://img.shields.io/badge/tests-1%2C281%20passing-brightgreen)]()
[![품질](https://img.shields.io/badge/gauntlet-A%E2%88%92%20(95%2F100)-blue)]()
[![GPU](https://img.shields.io/badge/GPU-CUDA%20supported-orange.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/iikarus/Dragon-Brain)](https://github.com/iikarus/Dragon-Brain/stargazers)

> **LongMemEval R@5 100%** · **34개의 MCP 도구** · **200ms 이하 하이브리드 검색** · **CI로 강제된 Fail-Loud 계약** · **LLM 필요 없음**

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
| **Fail-Loud 인프라** | 아니요 | 아니요 | **예 (`SearchError` 계약, CI 통제)** |

## 감사를 통한 단련 (Forged in Audit)

대부분의 오픈 소스 기억 시스템은 '해피 패스(happy path)'만을 포장합니다. 다음은 Dragon Brain이 프로덕션 환경에 2개월 동안 방치했던 버그와, 다시는 이런 일이 발생하지 않도록 구축된 인프라에 대한 이야기입니다.

### 거짓말 (The lie)

2026년 4월 이전의 `search()` 파이프라인은 대략 다음과 같았습니다.

```python
try:
    # ... 6채널 검색 파이프라인 ...
except Exception:
    return []
```

MCP의 `search_memory` 도구는 이후 `[]`를 `"No results found."`(결과를 찾을 수 없음)이라는 문자열로 변환했습니다. Claude는 이 문자열을 받고 그것을 권위 있는 사실로 취급했습니다—*"사용자는 이 주제에 대해 정말로 기억이 없다"*—하지만 실제로는 임베딩 서비스가 충돌했거나, FalkorDB에 연결할 수 없거나, Qdrant에서 타임아웃이 발생했을 수도 있습니다.

**저하된 쿼리가 발생할 때마다 AI는 자신이 문맥이 누락된 사실조차 모른 채 추론을 수행했습니다.** 이것은 진정한 "빈 결과"와 구별할 수 없는 자신감 넘치는 거짓말이었으며, 시스템에서 가장 많이 호출되는 함수에 하드코딩되어 있었습니다.

### 수정 (The fix)

4단계에 걸친 적대적 감사 결과 37개 소스 파일에서 **83개의 계약 위반**을 발견했습니다. 2026년 4월부터 5월까지 10차례에 걸쳐 수정 사항이 배포되었습니다.

- 인프라 오류는 이제 **`SearchError`**를 발생시킵니다—빈 목록은 이제 *오직* "결과를 찾을 수 없음"을 의미합니다.
- **MCP `search_memory`**는 구조화된 오류 `{"error": "MEMORY_LAYER_DEGRADED", "retry_safe": true}`를 반환합니다—AI에게 명확하게 성능 저하를 알리며 절대로 자신감 넘치는 거짓말을 하지 않습니다.
- 엔티티 생성/업데이트/삭제 시의 **크로스 스토어 보상**—Qdrant 쓰기 실패 시 FalkorDB를 롤백하여 스플릿 브레인 고립 항목을 방지합니다.
- **엣지 쓰기에 `CREATE` 대신 `MERGE` 사용**—재시도된 `create_relationship` 호출이 중복된 엣지를 생성하지 않습니다.
- **FTS 쓰기 실패는 호출자에게 전파됩니다**—인덱스가 조용히 구식이 되는 문제를 제거했습니다.
- **잠금 관리자는 경합 시 `TimeoutError`를 발생시킵니다**—잠금을 얻지 못한 채 조용히 진행되는 일은 절대 없습니다.
- **MCP 도구는 의미론적 유효성 검사를 거칩니다**—잘못된 UUID는 조용히 빈 결과를 반환하는 대신 `{"error": "ENTITY_NOT_FOUND"}`를 반환합니다.

### 마지노선을 지키는 규율 (The discipline)

- **`tox -e contracts`** — CI 게이트의 기준선이 **13개의 위반**으로 고정되었습니다(64개에서 감소). 새로운 위반 사항은 병합 전 빌드를 실패하게 만듭니다. 분기별 검토를 통해 이 기준선을 0에 가깝게 낮춥니다.
- **행위 기반 통합 테스트** — `testcontainers-python`은 실제 `falkordb/falkordb:v4.14.11` 및 `qdrant/qdrant:v1.16.3`을 스핀업하고 작업 중간에 `container.kill()`을 실행하여 종단 간 fail-loud 계약이 유지되는지 확인합니다.
- **네이티브 비동기 저장소** — `AsyncMemoryRepository`는 약 75개의 호출 사이트에서 동기식 데이터베이스 드라이버를 스레드 풀에 격리합니다.
- **신뢰 경계 문서화** — 모든 교차 프로세스 경계는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)에 명시적 계약으로 기록되어 있습니다.

### 이것이 중요한 이유

기억 계층이 자신의 실패 모드에 대해 거짓말을 할 수 있다면 하위의 모든 추론 단계가 오염됩니다. AI 에이전트는 도구를 신뢰합니다. 자신 있게 빈 결과를 조작하는 도구는 전체 추론 사슬을 독살합니다.

우리가 아는 한 Dragon Brain은 '큰 소리로 실패(fail-loud)'하는 동작을 CI로 강제하는 계약으로 취급하는 최초의 오픈 소스 기억 시스템입니다. 이 상황이 다시 발생하면 코드 병합 자체가 거부됩니다.

### 성적표 (Receipts)

- 106개의 테스트 파일에 걸친 **1,337개의 테스트**, 0개 실패, 0개 건너뜀
- **변이 테스트** — 27개 소스 파일에서 2,270개의 돌연변이 발생, 1,184개 제거 (각 함수당 3악/1슬픔/1기쁨)
- **속성 기반 테스트** — 38개의 Hypothesis 속성
- **퍼즈 테스트** — 30K+ 입력, 0번의 충돌
- **정적 분석** — mypy 엄격 모드(0 오류), ruff(0 오류)
- **보안 감사** — Cypher 주입 감사, 자격 증명 스캔
- **데드 코드 감지** — Vulture(발견 없음)
- **Dragon Brain Gauntlet** — 20라운드 자동 품질 감사, **A− (95/100)**

Gauntlet 전체 결과: [docs/GAUNTLET_RESULTS.md](docs/GAUNTLET_RESULTS.md) · 신뢰 경계: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · 통합 테스트: [tests/integration/test_db_kill_scenarios.py](tests/integration/test_db_kill_scenarios.py)

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
