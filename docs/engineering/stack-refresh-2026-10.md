# Stable dependency refresh — 1 October 2026

The frontend now uses React 19, React Router 7, Vite 8, TypeScript 7, and Node.js 24 LTS. Versions below were checked against npm and PyPI stable release metadata on 1 October 2026. The npm lockfile records the tested dependency tree; backend constraints admit compatible fixes within the tested major family, or minor family for 0.x packages.

| Component | Previous requirement | Tested requirement |
| --- | --- | --- |
| React / React DOM | 18.3.1 | 19.3.0 |
| React Router | 6.26 | 7.18.4 |
| Vite / React plugin | 5.4 / 4.3 | 8.3.2 / 6.1.1 |
| TypeScript | 5.9 | 7.0.2 |
| Node.js build/runtime | 20 | 24 LTS |
| Lucide | 0.441 | 1.49.0 |
| React Markdown | 9 | 10.1.0 |
| Recharts | 3.7 | 3.10.1 |
| Tailwind CSS | 3.4.12 | 3.4.19 |
| FastAPI / Uvicorn | >=0.115 / >=0.30 | >=0.142.2,<0.143 / >=0.54,<0.55 |
| Pydantic / settings | >=2.9 / >=2.5 | >=2.13.5,<3 / >=2.15,<3 |
| Anthropic / OpenAI SDK | >=0.34 / >=1.40 | >=1.11,<2 / >=3.22.1,<4 |
| Websockets | >=12 | >=17.1,<18 |
| Pillow | absent | >=12.3,<13 |
| YouTube transcript SDK | >=0.6 | >=1.2.4,<2 |
| Torch support / VPS wheel | >=2.1 | >=2.10,<2.15 / 2.14.1+cpu |
| NumPy, Python 3.11 | >=1.26 | >=2.4.6,<2.5 |
| NumPy, Python 3.12+ | >=1.26 | >=2.5.3,<3 |

The old backend minimums were unbounded, so existing fresh installs already resolved many of these newer releases. This change makes tested compatibility explicit rather than claiming every backend package was previously installed at its old minimum.

## Compatibility decisions

- Sandpack 2.20 declares React 19 peers; no force install or peer override is needed. The obsolete React Router 5 type package is removed because Router ships its own types.
- React 19 makes an untyped React element's `props` unknown. The markdown extractor supplies the child-prop type to `isValidElement`.
- Tailwind stays on the current 3.4 patch release. Tailwind 4 needs a separate stylesheet/configuration migration and visual review; changing only its dependency would break this theme.
- Python 3.11–3.13 remain in CI. NumPy 2.5 requires Python 3.12, so Python 3.11 uses the newest compatible 2.4 series.
- The YouTube 1.x SDK removed `get_transcript` and returns typed snippets. Ingestion now calls `YouTubeTranscriptApi().fetch` in a worker thread and reads `snippet.text`. The `[knowledge]` extra installs PDF/transcript dependencies; CI tests the actual SDK return shape.
- Anthropic 1.11 uses `httpx2` for custom HTTP clients; OpenAI 3.22 still accepts `httpx`. Existing provider constructors use each SDK's default client. Actual SDK requests and parsed responses were checked using their respective in-process mock transports, without model API charges.
- The VPS image installs the official CPU-only Torch wheel before other requirements. Build and CI assertions reject CUDA wheels. GPU training and Ruh serverless images are separate and unchanged by this Dockerfile.
- Explicit pip 26.2.1 and setuptools 84.0.0 replace inherited installer versions with published vulnerabilities. Runtime metadata assertions verify the final copied versions. Final image verification runs in GitHub CI.
- Docker contexts exclude host `node_modules`, build output, and local environment files. This prevents host dependencies from overwriting Alpine's native dependencies after `npm ci`.
- The Python wheel now ships `ruh_model` code needed by public tokenizer APIs, while excluding checkpoints and generated binary datasets. Installing the wheel does not require Torch unless the ML extra is selected.

## Verification

- Clean `npm ci`, TypeScript 7 `tsc --noEmit`, and Vite 8 production build passed.
- Frontend utility checks: 118 assertions across four scripts passed.
- Production assets rendered in Chromium at desktop/mobile sizes with API fixtures and no page errors.
- `npm audit`: zero known vulnerabilities after refreshing transitive versions.
- Isolated Python 3.12 install: 910 application tests passed; 8 optional tests skipped. Focused doctor, transcript, and security repairs: 40 passed.
- Provider SDK contract regressions call the actual SDK HTTP stacks and Mizan adapters, preserving structured tool schemas, arguments, text, and usage; neither test contacts a model API.
- Ruff lint/format and mypy across 137 backend source files passed.
- Node 24 Alpine frontend Docker build and CPU-only backend Docker build passed, using the official GCR mirror when Docker Hub rate-limited the cloud environment.
- The initial CPU image imported Torch, both provider SDKs, Pillow, the tokenizer, and Ruh model code; CUDA was absent. Container health returned 200 and anonymous status stayed 401. Its inherited installer audit identified pip/setuptools issues fixed in the final Dockerfile; the final installer-upgrade image is verified by CI.
- Fresh wheel installation outside the repository returned 200 for root analysis, tokenization, and Q28 features without importing Torch. Wheel contents contain no model weight files or Parquet/Arrow datasets.
- The isolated Python development environment's dependency audit reported no known vulnerabilities after updating its installer.

Test evidence is stored in `/workspace/parallel/stack` during this task. Those files contain no production data or model checkpoints. Repeated local image builds exhausted this environment's vfs storage, so final heavy Docker builds run on standard free GitHub runners. The disposable local smoke images and unused build cache were removed; model files and other agents' retained images were preserved.
