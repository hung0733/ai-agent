#!/usr/bin/env python
"""Trigger all enabled schedules immediately.

This script creates task records from all enabled schedule templates,
updates their last_run_at and next_run_at timestamps.

Usage:
    python scripts/trigger_all_schedules.py [--dry-run] [--no-scatter]

Options:
    --dry-run     Show what would be triggered without actually creating tasks
    --no-scatter  Execute immediately without random delay (default: scatter 0-300s)
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from croniter import croniter, CroniterBadCronError
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from db.config import async_session_factory
from db.dao.task_dao import TaskDAO
from db.dto.task import TaskCreate
from db.entity import ScheduleEntity, TaskEntity
from i18n import _
from scheduler.manager import ScheduleManager
from utils.timezone import now_server

# Scatter window for conflicting schedules (seconds)
_SCATTER_WINDOW = 300


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=_("Trigger all enabled schedules immediately"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=_("Show what would be triggered without creating tasks"),
    )
    parser.add_argument(
        "--no-scatter",
        action="store_true",
        help=_("Execute immediately without random delay"),
    )
    return parser.parse_args()


def calculate_next_run(cron_expression: str) -> datetime | None:
    """Calculate next run time from cron expression."""
    try:
        cron = croniter(cron_expression, now_server())
        return cron.get_next(datetime)
    except CroniterBadCronError as exc:
        print(f"  {_('錯誤')}：cron 表達式無效 — {exc}")
        return None
    except Exception as exc:
        print(f"  {_('錯誤')}：cron 解析失敗 — {exc}")
        return None


async def trigger_all_schedules(dry_run: bool = False, no_scatter: bool = False) -> None:
    """Trigger all enabled schedules."""
    async with async_session_factory() as session:
        # Load all enabled schedules with their task templates
        stmt = (
            select(ScheduleEntity)
            .where(ScheduleEntity.enabled.is_(True))
            .options(joinedload(ScheduleEntity.task))
        )
        result = await session.execute(stmt)
        schedules = list(result.scalars().all())

        if not schedules:
            print(_("沒有已啟用的 schedule。"))
            return

        print(_("找到 %d 個已啟用的 schedule：") % len(schedules))
        print()

        # Print summary
        for schedule in schedules:
            task = schedule.task
            print(f"  Schedule #{schedule.id}")
            print(f"    Cron: {schedule.cron_expression}")
            print(f"    Task: #{task.id if task else 'N/A'} — {task.name if task else 'N/A'}")
            print(f"    Type: {task.task_type if task else 'N/A'}")
            print(f"    Content: {task.content[:80] + '...' if task and len(task.content) > 80 else (task.content if task else 'N/A')}")
            print(f"    Agent ID: {task.agent_id if task else 'N/A'}")
            print(f"    Last run: {schedule.last_run_at}")
            print(f"    Next run: {schedule.next_run_at}")
            print()

        if dry_run:
            print(_("--dry-run 模式：不會創建 task record。"))
            return

        # Calculate delays
        if no_scatter:
            delays = [0.0] * len(schedules)
        else:
            delays = sorted([random.uniform(0, _SCATTER_WINDOW) for _ in schedules])

        print(_("開始觸發 schedule（scatter window: %d 秒）...") % _SCATTER_WINDOW)
        print()

        success_count = 0
        error_count = 0
        disabled_count = 0

        for schedule, delay in zip(schedules, delays):
            if delay > 0:
                print(f"  等待 {delay:.1f} 秒...")
                await asyncio.sleep(delay)

            task = schedule.task
            if not task:
                print(f"  Schedule #{schedule.id}: {_('錯誤')} — 沒有關聯的 task，跳過")
                error_count += 1
                continue

            # Calculate next run
            next_run = calculate_next_run(schedule.cron_expression)
            if next_run is None:
                print(f"  Schedule #{schedule.id}: {_('錯誤')} — cron 表達式無效，停用此 schedule")
                schedule.enabled = False
                await session.flush()
                disabled_count += 1
                continue

            # Create task record
            try:
                task_dto = TaskCreate(
                    name=task.name,
                    task_type=task.task_type,
                    content=task.content,
                    agent_id=task.agent_id,
                    parameters=task.parameters,
                    status="pending",
                    next_process_dt=now_server(),
                )
                task_dao = TaskDAO(session)
                entity = TaskEntity(**task_dto.model_dump())
                await task_dao.create(entity)

                # Mark schedule as executed
                schedule.last_run_at = now_server()
                schedule.next_run_at = next_run
                await session.flush()

                print(f"  ✓ Schedule #{schedule.id}: 已創建 task #{entity.id}，下次執行 {next_run}")
                success_count += 1

            except Exception as exc:
                print(f"  ✗ Schedule #{schedule.id}: {_('執行失敗')} — {exc}")
                error_count += 1
                await session.rollback()

        await session.commit()

        print()
        print("=" * 60)
        print(_("觸發完成："))
        print(f"  成功: {success_count}")
        print(f"  失敗: {error_count}")
        print(f"  停用: {disabled_count}")
        print("=" * 60)


async def main() -> None:
    args = parse_args()

    if args.dry_run:
        print(_("=== DRY RUN 模式 ==="))
        print()

    await trigger_all_schedules(dry_run=args.dry_run, no_scatter=args.no_scatter)


if __name__ == "__main__":
    asyncio.run(main())
