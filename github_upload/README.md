# GitHub 分片上传指南

> preson 仓库体积约 **3.5 GiB**，含 DuckDB、PDF 财报、书籍扫描件等大文件，无法一次性 `git push` 到 GitHub。
>
> 本目录提供 **shard 分片推送** + **大文件分片存储** 两套机制，解决 GitHub 100 MB 单文件限制与网络超时问题。
>
> **2026-06-21 简化**：剔除 `.backup/`（与活跃目录重复的历史快照）+ `_OCR可搜索版/`（PDF 原书的 OCR 副本，可用 ocrmypdf 重生成），shard 数量 9→8，待推总量 2.08 GiB → ~440 MiB。

**远程仓库**：`git@github.com:xjturmy/person.git`（私有）

**最后更新**：2026-06-21

---

## 策略概览

```
本地 main
    │
    ├─ subtree split ──→ 9 个 shard/* 分支（按目录拆分）
    │
    ├─ 并行/串行 push ──→ GitHub 远程 shard/* 分支
    │
    └─ read-tree 合并 ──→ 推送 main（或由 clone 方 merge_shards.sh 合并）
```

**大文件（>100 MB）** 不直接进 Git，而是：

1. `split_assets.py` 切分到 `.github_blob_store/`（每片 90 MB）
2. 分片随 `shard/blobs` 分支上传
3. clone 后 `merge_assets.py --restore-all` 还原到 `data/preson.duckdb` 等

---

## Shard 分支映射

| 分支 | 本地目录 | 约计大小 | 说明 |
|------|---------|---------|------|
| `shard/root` | 顶层 blob 文件 | ~50 KiB | 仅 `.gitignore`、`README.md`、`CLAUDE.md` 等 6 个文件，**不含** `data/` |
| `shard/tools` | `.tools/` | ~4.7 MiB | 脚本与 Dashboard |
| `shard/companies` | `02_companies/` | ~945 MiB | 公司档案 + PDF 财报 |
| `shard/knowledge` | `01_knowledge/` | ~440 MiB | 知识库 + PDF 书籍（已剔 `_OCR可搜索版/` 322 MiB） |
| `shard/macro` | `03_macro/` | ~233 KiB | 宏观与 ETF 数据 |
| `shard/blobs` | `.github_blob_store/` | ~214 MiB | DuckDB 等大文件分片 |
| `shard/config` | `.config/` | ~123 KiB | 配置（含敏感凭证，仓库须私有） |
| `shard/docs` | `docs/` | ~552 KiB | 项目文档与计划 |

> `.backup/` 已加入 `.gitignore`（2026-06-21 简化）：本地保留作应急副本，远程不再镜像；如需恢复，对照活跃目录 `01_knowledge/` `02_companies/` `03_macro/` 即可。

---

## 脚本清单

| 脚本 | 用途 |
|------|------|
| `prepare_push.sh` | 首次上传前：扫描并拆分超大文件 |
| `split_assets.py` | 将 >90 MB 文件切到 `.github_blob_store/` |
| `merge_assets.py` | clone 后从分片还原大文件 |
| `push_parallel.sh` | **主流程**：split → push shard → 合并 main |
| `push_in_batches.sh` | 备选：按 commit 批次递增推送 main（小仓库适用） |
| `merge_shards.sh` | **clone 方**：fetch 远程 shard 并合并为完整工作区 |

---

## 推送方：完整流程

### 0. 前置条件

```bash
cd /Users/gongyong/Desktop/Keyi/preson
source .venv/bin/activate

# 确认 remote
git remote -v
# 应指向 git@github.com:xjturmy/person.git

# macOS 脚本须为 Unix 换行（CRLF 会导致 bash 报错）
sed -i '' 's/\r$//' .tools/github_upload/*.sh
```

### 1. 首次：拆分超大文件

```bash
bash .tools/github_upload/prepare_push.sh
# 或
python3 .tools/github_upload/split_assets.py --apply --workers 4

git add .github_blob_store .tools/github_upload
git commit -m "chore: add blob store for GitHub upload"
```

### 2. 主流程：分片推送

**首次（含 subtree split，较慢）**：

```bash
PARALLEL=4 bash .tools/github_upload/push_parallel.sh
```

**重试 / 补推（本地 shard 分支已存在）**：

```bash
FORCE_ROOT=1 SKIP_SPLIT=1 PARALLEL=1 bash .tools/github_upload/push_parallel.sh
```

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `PARALLEL` | 4 | 同时 push 的分支数；大文件建议 `1` 防断线 |
| `SKIP_SPLIT` | — | `1` = 跳过 subtree split |
| `SKIP_MERGE` | — | `1` = 只 push shard，不合并 main |
| `FORCE_ROOT` | — | `1` = 重建 `shard/root`（修复误含 `data/` 的情况） |
| `REMOTE` | origin | 远程名 |

### 3. 补推单个失败分支

```bash
git push origin shard/knowledge:refs/heads/shard/knowledge   # ~762 MiB
git push origin shard/backup:refs/heads/shard/backup         # ~1.32 GiB
```

全部 shard 成功后，执行合并：

```bash
SKIP_SPLIT=1 PARALLEL=1 bash .tools/github_upload/push_parallel.sh
```

### 4. 验证

```bash
git ls-remote --heads origin 'refs/heads/shard/*'
git ls-remote origin refs/heads/main
# 应有 9 个 shard/* + 1 个 main
```

---

## Clone 方：还原完整工作区

### 方式 A：远程已有合并好的 main

```bash
git clone git@github.com:xjturmy/person.git preson && cd preson
python3 .tools/github_upload/merge_assets.py --restore-all
source .venv/bin/activate
```

### 方式 B：远程只有 shard 分支

```bash
git clone git@github.com:xjturmy/person.git preson && cd preson
bash .tools/github_upload/merge_shards.sh
python3 .tools/github_upload/merge_assets.py --restore-all
```

`merge_shards.sh` 会将各 shard 按前缀合并到 `workspace` 分支：

```
shard/root        → /
shard/tools       → .tools/
shard/companies   → 02_companies/
shard/knowledge   → 01_knowledge/
shard/macro       → 03_macro/
shard/blobs       → .github_blob_store/
shard/config      → .config/
shard/docs        → docs/
```

---

## DuckDB 大文件说明

| 项目 | 说明 |
|------|------|
| 原始文件 | `data/preson.duckdb`（~214 MB，Git 不跟踪） |
| 分片位置 | `.github_blob_store/data/preson.duckdb/part000…` |
| 单片大小 | 90 MB（GitHub 硬限 100 MB） |
| 清单 | `.github_blob_store/manifest.json`（含 SHA256） |
| 还原命令 | `python3 .tools/github_upload/merge_assets.py --restore-all` |

未还原时 Dashboard 会显示「CSV 兜底模式」。

---

## 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `set: pipefail: invalid option` | 脚本为 CRLF 换行 | `sed -i '' 's/\r$//' .tools/github_upload/*.sh` |
| `shard/root` 含 `preson.duckdb` 被拒 | root 分支误含 `data/` | `FORCE_ROOT=1 SKIP_SPLIT=1 bash push_parallel.sh` |
| `nothing added to commit`（旧版） | root 创建时文件名解析 bug | 已修复：仅用 `git ls-tree \| awk '$2=="blob"'` 取顶层文件 |
| `Connection reset by peer` | 大分支并行 push 超时 | 改 `PARALLEL=1`，或逐个 `git push origin shard/xxx` |
| SSH 连接失败 | 网络/VPN 不稳定 | 换 HTTPS：`git remote set-url origin https://github.com/xjturmy/person.git` |
| clone 后无 DuckDB | 未跑还原脚本 | `merge_assets.py --restore-all` |
| clone 后目录不全 | 部分 shard 未 push | 等推送方补推后 `git fetch` + 重跑 `merge_shards.sh` |

---

## 备选方案：按 commit 分批推送

适用于 commit 数量多、单次 push 体积可控的场景（**本仓库体积过大，首选 shard 方案**）：

```bash
BATCH_SIZE=3 SLEEP_SEC=2 bash .tools/github_upload/push_in_batches.sh
```

按 commit 递增推送 `main`，每批 3 个 commit，间隔 2 秒。

---

## 当前上传进度（2026-06-21 简化后）

| Shard | 状态 |
|-------|------|
| `shard/root` | ✅ |
| `shard/tools` | ✅ |
| `shard/macro` | ✅ |
| `shard/config` | ✅ |
| `shard/docs` | ✅ |
| `shard/blobs` | ✅ |
| `shard/companies` | ✅ |
| `shard/knowledge` | ❌ 待上传（~440 MiB，剔 OCR 副本后） |
| `shard/backup` | ⛔ 已弃用（.backup/ 加入 .gitignore） |
| `main` 合并 | ❌ 待 knowledge 推完后执行 |

**下一步**：

```bash
# 1) 重建 knowledge 分支（去除 _OCR可搜索版/ 后体积下降）
git branch -D shard/knowledge 2>/dev/null
git subtree split -P 01_knowledge -b shard/knowledge

# 2) 串行 push（440 MiB 单分支建议 PARALLEL=1）
PARALLEL=1 git push origin shard/knowledge:refs/heads/shard/knowledge

# 3) 合并 main（push_parallel.sh 已移除 shard/backup 映射）
SKIP_SPLIT=1 PARALLEL=1 bash .tools/github_upload/push_parallel.sh
```

---

## 相关文档

- 项目总览：[README.md](../../README.md)
- 工作区配置：[CLAUDE.md](../../CLAUDE.md)
