# 📰 Daily Paper Scout

[![Daily Paper Crawl](https://github.com/voidful/paper-daily/actions/workflows/daily-crawl.yml/badge.svg)](https://github.com/voidful/paper-daily/actions/workflows/daily-crawl.yml)

GitHub Actions 每日自動從 **6 個來源** 抓取 ML / AI / Speech 論文，去重合併後存成結構化 JSON。  
作為論文資料庫供 LLM（Grok、Claude、GPT 等）讀取並產出個人化篩選報告。

---

## ✨ Features

- 🕐 **每日自動執行** — GitHub Actions 在 UTC+8 08:30 自動抓取
- 🔀 **六來源聚合** — HuggingFace / arXiv / Semantic Scholar / Papers With Code / alphaXiv
- 🧹 **智慧去重** — 以 arXiv ID 為主鍵，合併多來源 metadata
- 📊 **預排序優先級** — 基於關鍵字命中、多來源交叉、社群熱度、追蹤作者
- 🤖 **LLM-Ready** — JSON 可直接被 Grok Task / Claude / GPT 讀取篩選

---

## 📁 目錄結構

```
paper-daily/
├── .github/workflows/
│   └── daily-crawl.yml      ← GitHub Actions 定時排程
├── scripts/
│   └── crawl.py              ← 爬蟲主程式
├── data/
│   ├── index.json             ← 所有日期的索引
│   ├── 2026-04-16.json        ← 當天所有論文（去重、預排序）
│   ├── 2026-04-15.json
│   └── ...
├── grok-task-prompt.md        ← Grok Task 用的 prompt 範本
├── .gitignore
└── README.md
```

---

## 📄 JSON 格式

### `data/index.json`

```json
{
  "latest": "2026-04-16",
  "entries": [
    {
      "date": "2026-04-16",
      "file": "2026-04-16.json",
      "total_papers": 185,
      "keyword_matched": 32,
      "crawled_at": "2026-04-16T00:30:00Z"
    }
  ]
}
```

### `data/{YYYY-MM-DD}.json`

```json
{
  "date": "2026-04-16",
  "crawled_at": "2026-04-16T00:30:00Z",
  "stats": {
    "sources": { "huggingface": 45, "arxiv_cs.CL": 80, "..." : "..." },
    "total_crawled": 350,
    "after_dedup": 280,
    "keyword_matched": 35
  },
  "papers": [
    {
      "id": "2406.12345",
      "title": "Neural Audio Codec with Semantic Alignment",
      "authors": ["Alice", "Bob"],
      "abstract": "We propose a novel ...",
      "sources": ["huggingface", "arxiv_cs.CL"],
      "url": "https://arxiv.org/abs/2406.12345",
      "keyword_hits": 5,
      "priority": 65.0,
      "upvotes": 12,
      "tracked_author": "Hung-yi Lee"
    }
  ]
}
```

---

## 🌐 資料來源

| Source | Method | Rate Limit | Notes |
|--------|--------|------------|-------|
| HuggingFace Daily Papers | REST API | None | 社群投票數 (`upvotes`) |
| arXiv (cs.CL, cs.SD, cs.AI, eess.AS) | Atom API | 3s interval | 按分類抓最新 80 篇 |
| arXiv keyword search | Atom API | 3s interval | 5 組關鍵字各抓 15 篇 |
| Semantic Scholar | Graph API v1 | 1s interval | 追蹤特定作者的最新論文 |
| Papers With Code | REST API v1 | None | 最新 50 篇 |
| alphaXiv trending | Web scraping | Best effort | 熱門論文排名 |

### 追蹤研究者

| Researcher | Semantic Scholar ID |
|------------|---------------------|
| Hung-yi Lee | `2364785` |
| Abdelrahman Mohamed | `40aborahman` |
| Shinji Watanabe | `1757803` |
| Kaiming He | `1771551` |

---

## 🔑 關鍵字系統

爬蟲會計算每篇論文的 `keyword_hits`，匹配的關鍵字涵蓋：

- **Audio/Speech**: audio codec, neural codec, TTS, ASR, voice cloning, HuBERT, wav2vec ...
- **Methods**: continual fine-tuning, inference-time scaling, early exit, DPO ...
- **Models**: LoRA, PEFT, multimodal, large language model, Qwen2-Audio ...

完整列表見 [`scripts/crawl.py`](scripts/crawl.py) 中的 `KEYWORDS` 變數。

---

## 🤖 LLM 讀取方式

### 直接讀取 Raw URL

```
https://raw.githubusercontent.com/voidful/paper-daily/main/data/index.json
https://raw.githubusercontent.com/voidful/paper-daily/main/data/{YYYY-MM-DD}.json
```

### 搭配 Grok Task

參考 [`grok-task-prompt.md`](grok-task-prompt.md) 的 prompt 範本，設定 Grok 每日自動讀取 JSON 並產出個人化論文報告。

### 篩選建議

| 欄位 | 用途 |
|------|------|
| `keyword_hits ≥ 3` | 強候選，與研究方向高度相關 |
| `priority ≥ 50` | 綜合評分高（多來源 + 關鍵字 + 熱度） |
| `tracked_author` 不為空 | 追蹤研究者的新論文 |
| `sources` 長度 ≥ 2 | 多平台同時出現，值得注意 |

---

## 🚀 Setup

### 使用方式（推薦）

1. **Fork** 這個 repository
2. GitHub Actions 會自動啟用
3. 每天 **UTC 00:30**（台北時間 08:30）自動執行爬蟲
4. 資料會自動 commit 到 `data/` 資料夾

> **不需要任何 API key。** 所有資料來源都使用公開 API。

### 手動觸發

到 **Actions → Daily Paper Crawl → Run workflow**，可以指定日期或留空使用今天。

### 本地開發

```bash
# 執行爬蟲
python scripts/crawl.py

# 指定日期
SCOUT_DATE=2026-04-15 python scripts/crawl.py
```

---

## 📊 排序邏輯

每篇論文的 `priority` 分數計算方式：

| 因子 | 加分 |
|------|------|
| 每個關鍵字命中 | +10 |
| 每多出現一個來源 | +15 |
| HuggingFace upvotes（上限 50） | +0.5/vote |
| 追蹤研究者 | +20 |
| 引用數（上限 100） | +0.1/cite |
| alphaXiv 趨勢排名 | +max(0, 20-rank) |

---

## 📝 License

MIT
