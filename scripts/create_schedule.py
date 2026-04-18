#!/usr/bin/env python
"""Create a scheduled task via command line.

Usage:
    python scripts/create_schedule.py \
        --name "Daily Weather Check" \
        --task-type "scheduled" \
        --content "Check weather and send report" \
        --agent-id 1 \
        --cron "0 9 * * *" \
        --parameters '{"location": "HK"}'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SAIntegrityError

from db.config import async_session_factory
from db.dao.agent_dao import AgentDAO
from db.dao.schedule_dao import ScheduleDAO
from db.dao.task_dao import TaskDAO
from db.dto.schedule import ScheduleCreate
from db.dto.task import TaskCreate
from db.entity import AgentEntity, ScheduleEntity, TaskEntity
from i18n import _
from utils.timezone import now_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=_("Create a scheduled task"))
    parser.add_argument("--name", required=True, help=_("Task name"))
    parser.add_argument("--task-type", required=True, help=_("Task type"))
    parser.add_argument("--content", required=True, help=_("Task content/prompt"))
    parser.add_argument("--agent-id", type=int, required=True, help=_("Agent ID"))
    parser.add_argument("--cron", required=True, help=_("Cron expression (e.g. '0 9 * * *')"))
    parser.add_argument("--parameters", default="{}", help=_("JSON parameters"))
    parser.add_argument("--parent-task-id", type=int, help=_("Parent task ID"))
    parser.add_argument("--execution-order", type=int, help=_("Execution order"))
    parser.add_argument("--required-skill", help=_("Required skill"))
    parser.add_argument("--enabled", action="store_true", default=True, help=_("Enable schedule"))
    parser.add_argument("--disabled", action="store_true", help=_("Create as disabled"))
    return parser.parse_args()


def calculate_next_run(cron_expression: str) -> datetime:
    """Calculate next run time from cron expression."""
    cron = croniter(cron_expression, now_server())
    return cron.get_next(datetime)


async def main() -> None:
    args = parse_args()

    # Validate cron expression
    try:
        next_run = calculate_next_run(args.cron)
    except Exception as exc:
        print(f"Error: Invalid cron expression '{args.cron}': {exc}")
        sys.exit(1)

    # Parse parameters
    try:
        parameters = json.loads(args.parameters)
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON parameters: {exc}")
        sys.exit(1)

    enabled = not args.disabled

    print(_("Creating scheduled task:"))
    print(f"  Name: {args.name}")
    print(f"  Type: {args.task_type}")
    print(f"  Agent ID: {args.agent_id}")
    print(f"  Cron: {args.cron}")
    print(f"  Next run: {next_run}")
    print(f"  Enabled: {enabled}")
    print(f"  Parameters: {args.parameters}")

    async with async_session_factory() as session:
        agent_dao = AgentDAO(session)
        task_dao = TaskDAO(session)
        schedule_dao = ScheduleDAO(session)

        # Validate agent exists
        stmt = select(AgentEntity).where(AgentEntity.id == args.agent_id)
        result = await session.execute(stmt)
        agent = result.scalar_one_or_none()

        if not agent:
            print(f"\n{_('錯誤')}：Agent ID {args.agent_id} 不存在於資料庫中。")
            # List available agents
            all_agents = await session.execute(select(AgentEntity))
            agents = all_agents.scalars().all()
            if agents:
                print(f"\n{_('可用的 Agent 列表：')}")
                print(f"  {'ID':<6} {'Name':<25} {'agent_id'}")
                print(f"  {'─' * 6} {'─' * 25} {'─' * 30}")
                for a in agents:
                    print(f"  {a.id:<6} {a.name:<25} {a.agent_id}")
                print(f"\n{_('請使用 --agent-id <ID> 指定正確的 agent。')}")
            else:
                print(f"\n{_('資料庫中沒有任何 agent。請先建立 agent。')}")
            sys.exit(1)

        # Create task
        task_dto = TaskCreate(
            name=args.name,
            task_type=args.task_type,
            content=args.content,
            agent_id=args.agent_id,
            parent_task_id=args.parent_task_id,
            execution_order=args.execution_order,
            required_skill=args.required_skill,
            status="pending",
            parameters=parameters if parameters else None,
            next_process_dt=next_run,
        )

        try:
            task = await task_dao.create_from_dto(task_dto)
        except SAIntegrityError as exc:
            error_msg = str(exc.orig) if hasattr(exc, "orig") else str(exc)
            print(f"\n{_('錯誤')}：無法創建任務 — 資料庫完整性違反。")
            if "foreign key" in error_msg.lower() or "fkey" in error_msg.lower():
                print(_("請確認所有外鍵引用的記錄都存在（agent_id, parent_task_id 等）。"))
            else:
                print(f"  詳細訊息：{error_msg}")
            sys.exit(1)

        print(f"\nCreated task (id={task.id})")

        # Create schedule
        schedule_dto = ScheduleCreate(
            task_id=task.id,
            cron_expression=args.cron,
            enabled=enabled,
            next_run_at=next_run,
        )
        schedule = await schedule_dao.create_from_dto(schedule_dto)
        print(f"Created schedule (id={schedule.id})")

        await session.commit()

    print(f"\nDone! Schedule created successfully.")


if __name__ == "__main__":
    asyncio.run(main())
