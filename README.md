# tieshan-photo — 鐵山誌老照片人臉辨識系統

鐵山誌專案的人臉偵測、嵌入、匹配與查詢模組。以 MCP server 形式運行，讓 Claude Code 在研究工作流中直接查詢「許天催出現在哪些照片」。

## 現況（2026-03-07）

| 指標 | 數值 |
|---|---|
| 照片總數 | 4,383 |
| 已掃描 | 4,325（98.7%） |
| 偵測人臉 | 33,112 |
| 已辨識人物 | 49 人（有 anchor） |
| 人物資料庫 | 108 人（含尚未建 anchor 者） |
| 自動匹配 | 9,559 張臉（28.9%） |
| Anchor 數 | 165 個 |
| TCMB 參考照片 | 102 張（已下載掃描） |

### 匹配數前十名

| 人物 | 匹配照片數 | anchors |
|---|---|---|
| 許雲陽 | 711 | 多 |
| 黃秀鸞 | 615 | 多 |
| 陳允 | 366 | 多 |
| 許天德 | 346 | 多 |
| 許雲鵬 | 322 | 多 |
| 許作宗 | 301 | 2 |
| 許作慶 | 285 | 2 |
| 許天象 | 282 | 多 |
| 許錫玉 | 266 | 3 |
| 林月英 | 256 | 多 |

## 運作原理

```
照片 → 前處理(CLAHE增強+去噪) → InsightFace偵測人臉
     → 每張臉產生 512 維嵌入向量 → 存入 SQLite
     → cosine similarity 比對 anchor → 自動匹配人物
```

### Anchor 機制

Anchor 是人工確認的「這張臉是某人」標記。系統拿 anchor 當標準答案，對所有未標記的臉做比對。

- 同一人可有多個 anchor（不同年齡、角度、照片品質）
- anchor 越多、越多樣，匹配越準
- 每次新增 anchor 自動觸發重新匹配

### 匹配閾值

| 等級 | cosine similarity | 意義 |
|---|---|---|
| HIGH | ≥ 0.45 | 幾乎確定同一人 |
| MEDIUM | ≥ 0.35 | 需人工確認（可能假陽性） |
| LOW | ≥ 0.25 | 僅供參考 |

### 老照片專用前處理

- CLAHE（clipLimit=2.0, tileGrid=8x8）— 褪色照片增強
- bilateral filter 去噪（保邊平滑）
- 長邊 > 2048px 縮放；< 640px 放大 2x（提升小臉偵測率）
- det_threshold 降至 0.3（預設 0.5，老照片需更寬容）

## 架構

```
tools/photo_server/
├── src/
│   ├── server.py          # FastMCP 主入口（port 8788）
│   ├── config.py          # 環境變數 + defaults
│   ├── db.py              # SQLite schema + CRUD
│   ├── pipeline.py        # detect → preprocess → embed → store
│   ├── matching.py        # cosine similarity 匹配
│   ├── preprocessing.py   # CLAHE + denoise 老照片增強
│   ├── persons.py         # 讀 family_tree.yaml + related_persons.yaml → DB
│   ├── photo_cards.py     # 解析 Vault 照片卡 → anchors
│   ├── log.py             # JSON lines logger
│   └── tools/
│       ├── photo_who.py   # 辨識照片中人物
│       ├── photo_find.py  # 找含某人的所有照片
│       ├── photo_stats.py # 掃描/標注進度
│       ├── photo_anchor.py # 標記已知人物
│       └── photo_cluster.py # 未標註臉孔分群
├── batch_scan.py          # 全量掃描腳本
├── download_models.py     # 下載 InsightFace 模型
├── pyproject.toml
├── data/                  # gitignored — face.db
├── models/                # gitignored — ONNX 模型 (~300MB)
└── tests/
```

## MCP Tools

### `photo_who` — 這張照片裡有誰？

輸入照片路徑，回傳每張偵測到的臉 + top-3 匹配人物。

### `photo_find` — 某人出現在哪些照片？

輸入人名或 person_id，回傳所有匹配照片（含分數、信心度）。

### `photo_stats` — 掃描進度

回傳總照片數、已掃描、人臉數、已匹配數、各人物統計。

### `photo_anchor` — 標記這張臉是某人

寫入 anchor，觸發自動重新匹配所有未標記人臉。

### `photo_cluster` — 未標註臉孔分群

DBSCAN 分群，回傳群組列表 + 樣本照片。

## 使用方式

### 啟動 server

```bash
cd tools/photo_server
uv run python src/server.py
# Server runs at http://127.0.0.1:8788/mcp
```

### 全量掃描

```bash
uv run python batch_scan.py              # 掃描 + 匹配
uv run python batch_scan.py --dry-run    # 只計數不掃描
uv run python batch_scan.py --match-only # 只跑匹配（不重新偵測）
```

### 下載模型

```bash
uv run python download_models.py
# 下載 InsightFace buffalo_l (~300MB)
```

## 人物資料來源

- `tools/family_tree.yaml` — 許家直系（許其琛以下五代）
- `tools/related_persons.yaml` — 姻親、日本友人、地方名士

兩個檔案在 server 啟動時自動載入 persons 表，共用 person_id 作為統一識別碼。

## 技術選型

| 項目 | 選擇 | 理由 |
|---|---|---|
| MCP 框架 | FastMCP | 裝飾器模式、自動 schema |
| HTTP 傳輸 | streamable-http (port 8788) | 與 TS server 同模式 |
| 偵測+嵌入 | InsightFace buffalo_l (RetinaFace + ArcFace 512d) | 對老照片容忍度高 |
| 儲存 | SQLite + numpy | 4,500 張照片不需向量資料庫 |
| 依賴管理 | uv + pyproject.toml | 快速、有 lockfile |
| Python | ≥ 3.11 | |

## 工作流程

1. **掃描**：`batch_scan.py` 跑全量偵測，嵌入向量存入 SQLite
2. **建 anchor**：透過 `photo_anchor` tool 或 Claude Code 對話，人工確認照片中人物
3. **自動匹配**：每次新增 anchor，系統自動比對所有未標記人臉
4. **查詢**：用 `photo_who`（這張照片有誰）或 `photo_find`（某人在哪些照片）
5. **迭代**：確認 MEDIUM 結果 → 新 anchor → 重新匹配 → 覆蓋率提升

## 已知限制

- 嬰幼兒臉與成人特徵差異大，跨年齡匹配假陽性較高
- 團體照小臉（<30px）偵測率較低
- 僅一個 anchor 時 MEDIUM 候選假陽性率高，建議每人至少 3 個 anchor
- 老照片嚴重褪色或模糊時偵測可能失敗（目前 57/4,267 = 1.3% 失敗率）

## 未來方向

- 接上國家文化記憶庫（TCMB）照片，跨資料庫比對
- MEDIUM 候選的人工確認回饋迴圈
- 照片卡自動回寫 `recognized_persons` 欄位
- 人物照片索引自動生成
