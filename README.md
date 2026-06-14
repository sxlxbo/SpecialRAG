<p align="center">
  <h1 align="center">📄 SpecialRAG</h1>
  <p align="center">
    <strong>基于目录层级的文档智能问答系统</strong>
    <br />
    PDF 按目录叶子节点自动切块 · 层级检索 · 原文溯源 · WebUI 对话
    <br />
    <sub>Powered by PageIndex + nanobot</sub>
  </p>
</p>

---

## 项目简介

SpecialRAG 是一个面向企业场景的文档问答系统。它利用 PDF 自带的目录结构将文档切分为最小粒度的语义单元（叶子节点章节），用户通过 WebUI 自然语言提问后，系统自动检索最相关的章节原文，交由大模型基于原文生成可溯源的答案。

**核心区别**：不同于传统的向量 RAG 方案，SpecialRAG 采用**目录层级切块**，每个切块天然具有完整的上下文边界和语义完整性，避免了固定长度切块导致的上下文断裂问题。

### 工作流程

```
┌──────────┐     ┌──────────────────┐     ┌─────────────────┐
│   PDF    │ ──▶ │  PageIndex 引擎   │ ──▶ │  doc_workspace/  │
│  上传    │     │  提取目录 → 切块   │     │  JSON 索引数据   │
└──────────┘     └──────────────────┘     └────────┬────────┘
                                                   │
                                                   ▼
┌──────────┐     ┌──────────────────┐     ┌─────────────────┐
│  WebUI   │ ◀── │  nanobot Agent   │ ◀── │  ChunkStore     │
│  提问    │     │  4 个 doc 工具    │     │  BM25 检索引擎   │
└──────────┘     └────────┬─────────┘     └─────────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │   大模型回答   │
                   │   + 来源溯源   │
                   └──────────────┘
```

每次回答末尾自动附带 **📄 参考来源**：

```
📄 参考来源

1. 《2024年度经营计划》→ 第三章 财务目标 > 3.1 营收规划 > 2024年度营收目标（第12-13页，node_id=0012）
```

---

## 核心特性

| 特性 | 说明 |
|------|------|
| 🔖 **目录级切块** | 按 PDF 原始目录层级切分，每个叶子节点 = 一个语义完整的最小切块 |
| 🔍 **关键词检索** | BM25 倒排索引，支持中英文混合搜索，无需 embedding / 向量数据库 |
| 🌲 **层级溯源** | 每个切块保留完整目录路径（一级 > 二级 > ... > 叶子），答案可追溯至具体章节 |
| 💬 **WebUI 对话** | 开箱即用的 React 聊天界面，支持多轮对话 |
| 📦 **多文档** | 支持索引多份 PDF / Markdown，workspace 自动累积 |
| 🐳 **Docker 部署** | 多阶段构建，一条命令启动 |
| 🔁 **可复现构建** | uv.lock 锁定 138 个依赖版本，跨环境一致 |

---

## 快速开始

### 环境要求

- **Python** ≥ 3.11
- **uv**（`pip install uv`）
- bun / npm（可选，仅构建 WebUI 时需要）

### 1. 克隆项目

```bash
git clone https://github.com/sxlxbo/SpecialRAG.git
cd SpecialRAG
```

### 2. 一键初始化

**Windows：**
```powershell
.\setup.ps1
```

**macOS / Linux：**
```bash
bash setup.sh
```

脚本自动完成：检查环境 → 安装依赖 → 确认 WebUI → 生成配置文件。

### 3. 配置 API Key

```bash
# Linux / macOS
export OPENAI_API_KEY=sk-xxxxxxxx

# Windows PowerShell
$env:OPENAI_API_KEY="sk-xxxxxxxx"
```

支持的模型厂商：OpenAI / Anthropic / DeepSeek / 通义千问 / 智谱 等。

> 使用公司内网 LLM 代理？编辑 `~/.nanobot/config.json` 中的 `providers` 字段。

### 4. 索引文档

```bash
uv run doc-index --pdf /path/to/document.pdf
uv run doc-index --pdf /path/to/another.pdf   # 追加索引，不覆盖
```

### 5. 启动服务

```bash
uv run doc-gateway
```

浏览器打开 **http://127.0.0.1:8765**，开始提问。

---

## Docker 部署

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY=sk-...

# 2. 构建镜像
docker compose build

# 3. 索引文档
mkdir pdfs && cp /path/to/docs/*.pdf pdfs/
docker compose run --rm index --pdf /data/document.pdf

# 4. 启动服务
docker compose up -d gateway
```

服务运行在 **http://localhost:8765**。

---

## 项目结构

```
SpecialRAG/
├── src/doc_rag/                  # 核心引擎
│   ├── chunk_store.py            #   ChunkStore：切块管理 + BM25 检索引擎
│   ├── nanobot_doc_tools.py      #   4 个 nanobot 工具（list/structure/search/chunk）
│   ├── tools.py                  #   工具工厂函数
│   └── cli.py                    #   命令行入口（doc-index / doc-gateway）
│
├── skills/document-qa/           # nanobot 技能：文档问答行为约束
│   └── SKILL.md                  #   强制检索流程 + 来源引用规范
│
├── docker/                       # Docker 入口脚本
│   └── entrypoint.sh             #   自动生成 nanobot 配置
│
├── PageIndex-main/               # 上游：PageIndex PDF 解析引擎
├── nanobot-main/                 # 上游：nanobot AI Agent 框架 + WebUI
│   └── nanobot/web/dist/         #   预编译的 WebUI（无需重新构建）
│
├── pyproject.toml                # uv 项目配置
├── uv.lock                       # 锁定依赖版本（138 包）
├── Dockerfile                    # 多阶段构建
├── docker-compose.yml            # Docker 编排
├── setup.sh / setup.ps1          # 一键初始化脚本
├── .env.example                  # 环境变量模板
└── 使用说明.md                    # 详细中文使用手册
```

---

## 检索工具说明

系统向大模型提供 4 个专用工具，Agent 自动按流程调用：

| 工具 | 用途 | 调用时机 |
|------|------|----------|
| `doc_list` | 列出所有已索引文档 | 用户提问时首先调用，确定目标文档 |
| `doc_structure` | 获取文档完整目录树 | 浏览章节结构，找到相关 section |
| `doc_search` | BM25 关键词搜索 | （可选）跨所有叶子节点搜索 |
| `doc_chunk` | 按 node_id 获取章节原文 | 确定相关章节后，取出全文供 LLM 参考 |

**Agent 行为由 `skills/document-qa/SKILL.md` 约束**，确保：永不凭记忆回答、每次检索原文、结尾标注来源层级。

---

## 配置参考

`~/.nanobot/config.json`：

```json
{
  "agents": {
    "defaults": {
      "model": "deepseek/deepseek-chat",
      "provider": "deepseek",
      "workspace": "./doc_workspace"
    }
  },
  "providers": {
    "deepseek": {
      "api_key": "sk-xxxxxxxx"
    }
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 8765
  }
}
```

---

## License

MIT
