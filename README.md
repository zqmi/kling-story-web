# Kling Story · 制作站

全栈工作台：从**大纲** → **分镜** → **画面描写**（含可灵生图）→ **旁白 TTS** → **导出**，前端为 **Vue 3 + Vite**，后端为 **FastAPI + PostgreSQL**，LLM 默认走 **DeepSeek（OpenAI 兼容）**。

更细的产品与接口说明见 [`docs/TECHNICAL.md`](docs/TECHNICAL.md)。

---

## 环境要求

| 组件 | 版本说明 |
|------|-----------|
| Node.js | **^20.19.0** 或 **≥22.12.0**（与 `package.json` 的 `engines` 一致） |
| Python | 建议 **3.11+**（需支持 `async` / 类型注解） |
| PostgreSQL | **16**（推荐用仓库内 Docker Compose 一键起库） |
| Docker | 可选；用于启动数据库容器 |

---

## 快速运行（本地开发）

需要同时跑：**数据库**、**后端 API**、**前端**。默认端口：**PostgreSQL 5433**（映射）、**API 8000**、**前端 5173**。

### 1. 启动 PostgreSQL

在 **`backend`** 目录执行：

```bash
cd backend
docker compose up -d
```

Compose 将数据库映射到本机 **5433**（避免与常见本机 5432 冲突）。若你改用本机已有 Postgres，请把下面 `.env` 里的 `DATABASE_URL` 端口改成 **5432** 等实际值。

### 2. 配置后端环境变量

```bash
cd backend
copy .env.example .env
```

（Linux / macOS 使用 `cp .env.example .env`。）

编辑 **`backend/.env`**，至少填写：

- **`DEEPSEEK_API_KEY`**：编剧 / 分镜 / 描写等 LLM 能力需要（[DeepSeek 开放平台](https://platform.deepseek.com)）。
- **可灵生图**（单镜出图等）：在 `.env` 中配置 `KLING_ACCESS_KEY` + `KLING_SECRET_KEY`，或按你接入方式配置 `KLING_API_KEY` 等（详见 `backend/app/core/config.py` 中的变量名与默认值）。

`DATABASE_URL` 若与 Docker Compose 一致，可保持示例中的 **5433**。

### 3. 安装并启动后端

```bash
cd backend
python -m venv .venv
```

**Windows（PowerShell / CMD）：**

```bat
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**macOS / Linux：**

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

健康检查：<http://127.0.0.1:8000/health>

### 4. 安装并启动前端

在仓库**根目录**（与 `package.json` 同级）：

```bash
npm install
npm run dev
```

浏览器打开终端里提示的地址（一般为 <http://localhost:5173>）。开发模式下，Vite 会把 `/api`、`/projects`、`/health`、`/media` 代理到 **http://127.0.0.1:8000**（见 `vite.config.js`），因此**无需**单独给前端配 API 基地址即可联调。

---

## 常用脚本

| 目录 | 命令 | 说明 |
|------|------|------|
| 仓库根目录 | `npm run dev` | 前端开发服务器（热更新） |
| 仓库根目录 | `npm run build` | 生产构建，输出 `dist/` |
| 仓库根目录 | `npm run preview` | 本地预览构建结果（默认端口 4173，亦在 CORS 白名单内） |
| `backend` | `uvicorn main:app --reload --port 8000` | 后端 API |

---

## 环境变量摘要（后端）

以下在 **`backend/.env`** 中配置（完整列表与默认值见 `backend/app/core/config.py`）。

| 变量 | 作用 |
|------|------|
| `DATABASE_URL` | 异步 PostgreSQL 连接串（默认端口 **5433** 对应本仓库 Docker） |
| `DEEPSEEK_API_KEY` | LLM（OpenAI 兼容接口） |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | 可选，覆盖默认 DeepSeek 地址与模型名 |
| `KLING_*` | 可灵文生图相关（Access/Secret 或 API Key 等） |
| `EDGE_TTS_VOICE` | Edge TTS 音色（可选） |

**注意：** 勿将 `.env` 提交到 Git；仓库已通过 `.gitignore` 忽略 `backend/.env`。

---

## 仓库结构（简要）

```
kling-story-web/
├── src/                 # Vue 前端（路由、视图、API 封装）
├── vite.config.js       # 开发代理 → localhost:8000
├── package.json
├── backend/
│   ├── app/             # FastAPI 应用、路由、服务、模型
│   ├── main.py          # Uvicorn 入口：main:app
│   ├── requirements.txt
│   ├── docker-compose.yml
│   └── .env.example
└── docs/
    └── TECHNICAL.md     # 技术说明（产品边界、流水线等）
```

---

## 故障排除

- **前端接口全失败**：确认后端已在 **8000** 启动，且数据库已就绪（Docker `docker compose ps` 或本机 Postgres）。
- **`dubious ownership`（Git）**：在仓库目录执行一次  
  `git config --global --add safe.directory F:/2026/agent/kling-story-web`  
  （路径改为你的实际绝对路径。）
- **换行符警告（LF / CRLF）**：Windows 下常见，一般不影响运行；若需统一为 LF，可将 Git `core.autocrlf` 设为 `false` 并在编辑器中使用 LF。

---

## 许可证

若需对外开源，请在本仓库补充 `LICENSE` 文件并在此处更新说明。
