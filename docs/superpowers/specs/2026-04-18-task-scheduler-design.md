# Task Scheduler Design Spec

## Date
2026-04-18

## Purpose
實現 heap-based task scheduler，每秒 check 一次，到時就創建 task record。如果同一時間有多過 1 個 schedule task 要 run，就平均地 random 式喺 5 分鐘內執行，防止同時間 run 多個 task。

## Architecture

### Core Components

1. **`backend/scheduler/scheduler.py`** — `TaskScheduler` 類
   - 管理 min-heap，按 `next_run_at` 排序
   - 主循環：計算到最近 schedule 嘅時間，sleep 到嗰一刻，然後處理
   - 最多每 60 秒 wake up 一次以檢查 DB 變更

2. **`backend/scheduler/manager.py`** — `ScheduleManager` 類
   - DB 操作：載入所有 enabled schedule、更新 `next_run_at` / `last_run_at`
   - 創建 task record

3. **`backend/api/app.py`** — 修改
   - 加入 startup/shutdown event 嚟管理 scheduler 生命周期

4. **`requirements.txt`** — 修改
   - 加入 `croniter>=1.3.0`

## Data Flow

```
App 啟動
  → ScheduleManager.load_enabled_schedules()
  → TaskScheduler 將 schedule 載入 min-heap
  → 主循環開始：
      → 計算到最近 schedule 嘅時間差
      → 如果 < 1 秒，立即處理
      → 否則 sleep 到嗰個時間（最多 60 秒）
      → wake up 後處理所有到期 schedule
      → 用 croniter 計算新嘅 next_run_at
      → 更新 DB 同 heap
```

## Schedule Processing

### Due Schedule Detection
- 從 heap 取出所有 `next_run_at <= now()` 嘅 schedule
- 如果 heap 空咗，等待 60 秒後 reload

### Task Record Creation
- 為每個到期 schedule 創建 TaskEntity record
- 使用 schedule 關聯嘅 task 模板數據（name, content, agent_id, parameters 等）

### Next Run Calculation
- 使用 croniter 解析 cron_expression
- 計算下一個執行時間
- 更新 schedule 嘅 `next_run_at` 同 `last_run_at`

### Conflict Resolution (打散邏輯)
當 N 個 schedule 同時到期：
- N=1：立即處理
- N>1：生成 N 個隨機時間點（0~300 秒），排序後逐一分配
- 每個 schedule 嘅 `next_run_at` 用 croniter 計算，確保下次唔會撞期

## Error Handling

- DB 連接失敗：log error，等待 5 秒後重試
- croniter 解析失敗：log error，disable 該 schedule
- Task record 創建失敗：log error，保留原 next_run_at，下次重試
- 所有錯誤都使用 i18n `_()` 包裹

## Testing

- Unit tests for croniter integration
- Unit tests for heap management
- Unit tests for conflict resolution (打散邏輯)
- Integration tests with mock DB

## Dependencies

- `croniter>=1.3.0` — cron expression parsing
- Existing `ScheduleDAO`, `TaskDAO`, `ScheduleEntity`, `TaskEntity`
