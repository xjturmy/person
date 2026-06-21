# 理杏仁与财报技能（分享版）

本目录从个人理财知识库的 Cursor **Skill** 导出，便于学习交流。**请勿将真实 Token、账号密码写入文档或提交到公开仓库。**

## 目录说明

| 文件夹 | 内容 |
|--------|------|
| `lixinger-wide-archiver/` | 理杏仁开放 API 拉取估值宽表、财务指标、CSV→MD、一键流水线；**`SKILL.md`** 为使用说明，**`理杏仁开放API接口摘录.md`** 为接口与字段汇总；**`scripts/`** 为可执行 Python 脚本 |
| `company-financial-report-download/` | A 股巨潮、港股披露易财报 PDF 下载；**`SKILL.md`** 为使用说明，**`巨潮与披露易接口摘录.md`** 为公开接口要点；**`scripts/`** 为脚本 |

## 如何使用脚本（推荐）

1. **知识库根目录**：你的资料库根目录应包含 `02_公司档案库/`、（理杏仁流程还需要）根目录下的 `extract_recent_data.py` 等；与原作者仓库结构一致最省事。
2. **放置 skill**：将本分享包内的 `lixinger-wide-archiver`、`company-financial-report-download` **整个文件夹**复制到你的知识库 `.cursor/skills/` 下（若你不用 Cursor，可放在任意固定路径，并自行修改命令中的路径）。
3. **依赖**：理杏仁脚本需要 Python 3 + `requests`（可用 `pip install requests` 或 venv）。财报下载脚本主要用标准库 `urllib`。
4. **Token**：理杏仁 Token 在官网开放平台申请：见 `理杏仁开放API接口摘录.md` 中的官方链接；建议仅使用环境变量 `LIXINGER_TOKEN`，勿写入文件。

## 官方文档（必读）

- 理杏仁开放 API 文档与 Token：<https://www.lixinger.com/open/api/>（页面可能随官网调整，以实际为准）
- 巨潮、港交所：以各平台最新用户条款与 robots/声明为准；批量请求请限速、勿施压。

## 版本说明

- 导出日期以 Git/文件修改时间为准；接口字段以理杏仁、巨潮官网为准，若官网变更需自行对照更新脚本与摘录文档。
