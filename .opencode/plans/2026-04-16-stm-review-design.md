# STM Review Spec — Short-Term Memory Summary Workflow

## Overview

當對話歷史的 token 總和超過指定閾值時，自動將舊對話壓縮成結構化摘要，並寫入 `short_term_mem` 表，同時標記已處理的 `agent_msg_hist` 記錄，避免重複 summary。

## Requirements

### R1: 觸發條件
- 當 `session_db_id` 對應的 `agent_msg_hist` 中 `is_stm_summary=False` 的記錄總 token > `stm_trigger_token` 時觸發

### R2: 保留範圍
- 保留最新 `stm_trigger_token - stm_summary_token` token 的記錄（不做 summary）
- 其餘較舊的記錄全部進入 summary 流程

### R3: Checkpoint 分組
- 同一 `checkpoint_id` 的記錄視為同一組對話
- 要麼全部保留，要麼全部 summary，不可拆散

### R4: Summary 內容格式
- 只包含 `msg_type IN ('human', 'ai')` 的記錄
- 打包格式：`[YYYY-MM-DD HH:MM:SS] {sender} : {content}`（使用 `create_dt`）

### R5: 分批處理
- 每次 summary 的對話內容不超過 `max_token`（預設 30000）
- 如果待 summary 內容超過 `max_token`，分多次處理（由新到舊），直到全部處理完

### R6: LLM 輸出格式
```json
{
  "memories": [
    {
      "lossless_restatement": "User fixed a concurrency bug in the connection pool logic.",
      "record_dt": "2026-04-14T11:15:00"
    }
  ]
}
```

### R7: 寫入 Short-Term Memory
- 每條 `lossless_restatement` 寫入 `short_term_mem` 表：
  - `session_id = session_db_id`
  - `content = lossless_restatement`
  - `create_dt = record_dt`（從 JSON 取，如缺失則用當前時間）
  - `token = get_token_count(lossless_restatement)`

### R8: 標記已處理
- 將被 summary 的 checkpoint 中的**所有記錄**（包括 human、ai、tool、system 等所有 msg_type）標記為 `is_stm_summary=True`

### R9: 錯誤處理
- LLM 呼叫失敗：log error 並返回
- JSON 解析失敗：log error 並返回
- 缺 `record_dt`：用當前時間補上

### R10: 返回值
- 無返回值（`None`）

## Architecture

### Data Flow
```
agent_msg_hist (is_stm_summary=False)
  → 按 checkpoint_id 分組
  → 計算總 token
  → 如果 > stm_trigger_token:
    → 保留最新 (stm_trigger_token - stm_summary_token) token 的 checkpoint
    → 其餘 checkpoint 進入 summary
    → 分批處理（每批 ≤ max_token）
    → 呼叫 LLM
    → 解析 JSON
    → 寫入 short_term_mem
    → 標記 is_stm_summary=True
```

### Components
- `review_stm()` — 主函數，位於 `backend/agent/summary.py`
- `apply_stm_prompt_template()` — prompt 生成，位於 `backend/agent/prompt.py`
- `AgentMsgHistDAO` — 數據訪問，位於 `backend/db/dao/agent_msg_hist_dao.py`
- `ShortTermMemDAO` — 數據訪問，位於 `backend/db/dao/short_term_mem_dao.py`
- `Tools.get_token_count()` — token 計算，位於 `backend/utils/tools.py`

## Error Handling

| 錯誤情境 | 處理方式 |
|----------|----------|
| 無 `is_stm_summary=False` 記錄 | 直接返回 |
| 總 token ≤ `stm_trigger_token` | 直接返回 |
| LLM 呼叫失敗 | log error，返回 |
| JSON 解析失敗 | log error，返回 |
| `record_dt` 缺失 | 用當前時間補上 |
| 資料庫寫入失敗 | log error，繼續處理下一批 |
