"""Contact form messages.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 17:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column(
            "topic",
            sa.Enum(
                "question", "order", "kitchen", "safety", "feedback",
                name="contact_topic", native_enum=False, create_constraint=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "topic IN ('question', 'order', 'kitchen', 'safety', 'feedback')", name=op.f("ck_contact_messages_contact_topic")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_contact_messages_user_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["handled_by"], ["users.id"], name=op.f("fk_contact_messages_handled_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_messages")),
    )
    op.create_index(op.f("ix_contact_messages_created_at"), "contact_messages", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_contact_messages_created_at"), table_name="contact_messages")
    op.drop_table("contact_messages")
