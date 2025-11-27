"""Add previous_ip column to face_location_log table

Revision ID: add_previous_ip
Revises: 
Create Date: 2025-11-27 07:00:00.000000

"""
import sqlalchemy as sa

from CTFd.plugins.migrations import get_columns_for_table

# revision identifiers, used by Alembic.
revision = "add_previous_ip"
down_revision = None
branch_labels = None
depends_on = None


def upgrade(op=None):
    if op is None:
        # If op is None, we're being called from create_all, skip migration
        return
    
    columns = get_columns_for_table(
        op=op, table_name="face_location_log", names_only=True
    )
    
    # Add previous_ip column if it doesn't exist
    if "previous_ip" not in columns:
        op.add_column(
            "face_location_log",
            sa.Column("previous_ip", sa.String(length=46), nullable=True),
        )


def downgrade(op=None):
    if op is None:
        return
    
    columns = get_columns_for_table(
        op=op, table_name="face_location_log", names_only=True
    )
    
    # Remove previous_ip column if it exists
    if "previous_ip" in columns:
        op.drop_column("face_location_log", "previous_ip")

