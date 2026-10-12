"""create google_accounts

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('google_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('refresh_token', sa.String(length=512), nullable=False),
    sa.Column('scopes', sa.String(length=256), nullable=False),
    sa.Column('connected_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('google_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_google_accounts_user_id'), ['user_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('google_accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_google_accounts_user_id'))

    op.drop_table('google_accounts')
