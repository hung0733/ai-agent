"""fix invalid checkpoint_id format to uuid hex

Revision ID: 010_fix_checkpoint_id
Revises: 009_add_agent_type
Create Date: 2026-04-22 19:55:00.000000

將非 UUID hex 格式的 checkpoint_id 轉換為合法格式。
LangGraph 內部使用 binascii.unhexlify(checkpoint["id"].replace("-", "")) 解析 ID，
要求 checkpoint_id 必須是純十六進制字符串。

注意：此 migration 已手動執行，資料庫中的 60 個無效 ID 已修復。
"""
from typing import Sequence, Union

import uuid
from alembic import op
import sqlalchemy as sa

revision = '010_fix_checkpoint_id'
down_revision = '009_add_agent_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_valid_hex(s: str) -> bool:
    """檢查字符串是否為有效的十六進制格式。"""
    try:
        bytes.fromhex(s)
        return True
    except ValueError:
        return False


def upgrade() -> None:
    """修復所有非 hex 格式的 checkpoint_id。"""
    conn = op.get_bind()
    
    # 找出所有不符合 hex 格式的 checkpoint_id
    result = conn.execute(sa.text(
        "SELECT DISTINCT checkpoint_id FROM agent_msg_hist"
    ))
    invalid_ids = [row[0] for row in result if not _is_valid_hex(row[0])]
    
    if invalid_ids:
        print(f"發現 {len(invalid_ids)} 個無效的 checkpoint_id:")
        for cid in invalid_ids:
            print(f"  - {cid}")
        
        # 為每個無效 ID 生成新的 UUID hex 並更新
        for old_id in invalid_ids:
            new_id = uuid.uuid4().hex
            conn.execute(sa.text(
                "UPDATE agent_msg_hist SET checkpoint_id = :new_id WHERE checkpoint_id = :old_id"
            ), {"new_id": new_id, "old_id": old_id})
            print(f"  已將 '{old_id}' 轉換為 '{new_id}'")
        
        conn.commit()
        print("修復完成！")
    else:
        print("所有 checkpoint_id 均為有效 hex 格式，無需修復。")


def downgrade() -> None:
    """無法回退 — 原始非 hex 格式的 ID 已丟失。"""
    print("此 migration 無法安全回退（原始非 hex ID 已被替換為 UUID）。")
