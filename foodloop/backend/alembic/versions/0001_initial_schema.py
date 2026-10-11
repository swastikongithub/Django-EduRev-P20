"""Initial FoodLoop schema: users, sessions, providers, listings, reservations, audit log.

Revision ID: 0001
Revises: 
Create Date: 2026-10-11 17:30:05.472285

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('role', sa.Enum('customer', 'provider', 'admin', name='user_role', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('customer', 'provider', 'admin')", name=op.f('ck_users_user_role')),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_users_email_lowercase')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('audit_log',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.String(length=60), nullable=False),
    sa.Column('entity_type', sa.String(length=30), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_log_actor_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index(op.f('ix_audit_log_created_at'), 'audit_log', ['created_at'], unique=False)
    op.create_index('ix_audit_log_entity', 'audit_log', ['entity_type', 'entity_id'], unique=False)
    op.create_table('providers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=140), nullable=False),
    sa.Column('kind', sa.Enum('college_canteen', 'cafeteria', 'hostel_mess', 'pg_kitchen', 'other', name='provider_kind', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('address_line', sa.String(length=200), nullable=False),
    sa.Column('area', sa.String(length=100), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('pincode', sa.String(length=6), nullable=False),
    sa.Column('contact_phone', sa.String(length=20), nullable=False),
    sa.Column('fssai_number', sa.String(length=14), nullable=False),
    sa.Column('fssai_kind', sa.Enum('registration', 'state_licence', 'central_licence', name='fssai_kind', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('fssai_valid_until', sa.Date(), nullable=False),
    sa.Column('pickup_instructions', sa.Text(), server_default='', nullable=False),
    sa.Column('status', sa.Enum('pending', 'approved', 'rejected', 'suspended', name='provider_status', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('status_reason', sa.Text(), nullable=True),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_sample', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("fssai_kind IN ('registration', 'state_licence', 'central_licence')", name=op.f('ck_providers_fssai_kind')),
    sa.CheckConstraint("fssai_number ~ '^[0-9]{14}$'", name=op.f('ck_providers_fssai_number_format')),
    sa.CheckConstraint("kind IN ('college_canteen', 'cafeteria', 'hostel_mess', 'pg_kitchen', 'other')", name=op.f('ck_providers_provider_kind')),
    sa.CheckConstraint("pincode ~ '^[1-9][0-9]{5}$'", name=op.f('ck_providers_pincode_format')),
    sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'suspended')", name=op.f('ck_providers_provider_status')),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name=op.f('fk_providers_reviewed_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_providers')),
    sa.UniqueConstraint('slug', name=op.f('uq_providers_slug'))
    )
    op.create_index(op.f('ix_providers_status'), 'providers', ['status'], unique=False)
    op.create_table('sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_sessions_token_hash'))
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('listings',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('provider_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=80), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('meal_type', sa.Enum('breakfast', 'lunch', 'snacks', 'dinner', 'bakery', 'beverages', name='meal_type', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('diet', sa.Enum('veg', 'egg', 'non_veg', 'vegan', name='diet', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('allergens', postgresql.ARRAY(sa.String(length=20)), server_default='{}', nullable=False),
    sa.Column('allergen_note', sa.String(length=200), server_default='', nullable=False),
    sa.Column('image_path', sa.String(length=255), nullable=True),
    sa.Column('image_is_representative', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('original_price_paise', sa.Integer(), nullable=False),
    sa.Column('price_paise', sa.Integer(), nullable=False),
    sa.Column('quantity_total', sa.Integer(), nullable=False),
    sa.Column('quantity_available', sa.Integer(), nullable=False),
    sa.Column('max_per_order', sa.Integer(), server_default=sa.text('2'), nullable=False),
    sa.Column('storage', sa.Enum('hot_held', 'refrigerated', 'room_temp', 'shelf_stable', name='storage', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('prepared_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('pickup_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('pickup_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('safe_until', sa.DateTime(timezone=True), nullable=False),
    sa.Column('pickup_instructions', sa.Text(), server_default='', nullable=False),
    sa.Column('status', sa.Enum('draft', 'active', 'paused', 'removed', name='listing_status', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('removed_reason', sa.Text(), nullable=True),
    sa.Column('removed_by', sa.Uuid(), nullable=True),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('safety_declared_by', sa.Uuid(), nullable=False),
    sa.Column('safety_declared_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("allergens <@ ARRAY['gluten', 'crustacean', 'egg', 'fish', 'peanut', 'tree_nut', 'soy', 'milk', 'sulphite', 'sesame', 'mustard']::varchar[]", name=op.f('ck_listings_allergens_known')),
    sa.CheckConstraint("diet IN ('veg', 'egg', 'non_veg', 'vegan')", name=op.f('ck_listings_diet')),
    sa.CheckConstraint("meal_type IN ('breakfast', 'lunch', 'snacks', 'dinner', 'bakery', 'beverages')", name=op.f('ck_listings_meal_type')),
    sa.CheckConstraint("status IN ('draft', 'active', 'paused', 'removed')", name=op.f('ck_listings_listing_status')),
    sa.CheckConstraint("storage IN ('hot_held', 'refrigerated', 'room_temp', 'shelf_stable')", name=op.f('ck_listings_storage')),
    sa.CheckConstraint('max_per_order >= 1', name=op.f('ck_listings_max_per_order_positive')),
    sa.CheckConstraint('original_price_paise > 0', name=op.f('ck_listings_original_price_positive')),
    sa.CheckConstraint('prepared_at <= pickup_start AND pickup_start < pickup_end AND pickup_end <= safe_until', name=op.f('ck_listings_time_order')),
    sa.CheckConstraint('price_paise > 0 AND price_paise <= original_price_paise', name=op.f('ck_listings_price_valid')),
    sa.CheckConstraint('quantity_available >= 0 AND quantity_available <= quantity_total', name=op.f('ck_listings_quantity_available_range')),
    sa.CheckConstraint('quantity_total > 0', name=op.f('ck_listings_quantity_total_positive')),
    sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], name=op.f('fk_listings_provider_id_providers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['removed_by'], ['users.id'], name=op.f('fk_listings_removed_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['safety_declared_by'], ['users.id'], name=op.f('fk_listings_safety_declared_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_listings'))
    )
    op.create_index(op.f('ix_listings_meal_type'), 'listings', ['meal_type'], unique=False)
    op.create_index(op.f('ix_listings_price_paise'), 'listings', ['price_paise'], unique=False)
    op.create_index(op.f('ix_listings_provider_id'), 'listings', ['provider_id'], unique=False)
    op.create_index('ix_listings_status_pickup_end', 'listings', ['status', 'pickup_end'], unique=False)
    op.create_table('provider_members',
    sa.Column('provider_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('member_role', sa.Enum('owner', 'staff', name='member_role', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("member_role IN ('owner', 'staff')", name=op.f('ck_provider_members_member_role')),
    sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], name=op.f('fk_provider_members_provider_id_providers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_provider_members_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('provider_id', 'user_id', name=op.f('pk_provider_members')),
    sa.UniqueConstraint('user_id', name=op.f('uq_provider_members_user_id'))
    )
    op.create_table('reservations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('pickup_code', sa.String(length=6), nullable=False),
    sa.Column('customer_id', sa.Uuid(), nullable=False),
    sa.Column('listing_id', sa.Uuid(), nullable=False),
    sa.Column('provider_id', sa.Uuid(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_price_paise', sa.Integer(), nullable=False),
    sa.Column('total_paise', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('reserved', 'collected', 'cancelled', 'no_show', name='reservation_status', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('pickup_deadline', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payment_method', sa.Enum('pay_at_pickup', 'mock_online', name='payment_method', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('payment_status', sa.Enum('unpaid', 'paid', 'refunded', name='payment_status', native_enum=False, create_constraint=False, length=32), nullable=False),
    sa.Column('idempotency_key', sa.Uuid(), nullable=True),
    sa.Column('cancelled_by', sa.Enum('customer', 'provider', 'admin', 'system', name='cancelled_by', native_enum=False, create_constraint=False, length=32), nullable=True),
    sa.Column('cancel_reason', sa.Text(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('collected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('collected_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("cancelled_by IN ('customer', 'provider', 'admin', 'system')", name=op.f('ck_reservations_cancelled_by')),
    sa.CheckConstraint("payment_method IN ('pay_at_pickup', 'mock_online')", name=op.f('ck_reservations_payment_method')),
    sa.CheckConstraint("payment_status IN ('unpaid', 'paid', 'refunded')", name=op.f('ck_reservations_payment_status')),
    sa.CheckConstraint("status IN ('reserved', 'collected', 'cancelled', 'no_show')", name=op.f('ck_reservations_reservation_status')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_reservations_quantity_positive')),
    sa.CheckConstraint('total_paise = unit_price_paise * quantity', name=op.f('ck_reservations_total_matches')),
    sa.ForeignKeyConstraint(['collected_by'], ['users.id'], name=op.f('fk_reservations_collected_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['users.id'], name=op.f('fk_reservations_customer_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], name=op.f('fk_reservations_listing_id_listings'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], name=op.f('fk_reservations_provider_id_providers'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reservations')),
    sa.UniqueConstraint('customer_id', 'idempotency_key', name='uq_reservations_customer_idempotency'),
    sa.UniqueConstraint('pickup_code', name=op.f('uq_reservations_pickup_code'))
    )
    op.create_index(op.f('ix_reservations_customer_id'), 'reservations', ['customer_id'], unique=False)
    op.create_index(op.f('ix_reservations_listing_id'), 'reservations', ['listing_id'], unique=False)
    op.create_index(op.f('ix_reservations_provider_id'), 'reservations', ['provider_id'], unique=False)
    op.create_index(op.f('ix_reservations_status'), 'reservations', ['status'], unique=False)
    op.create_index('uq_reservations_one_active_per_listing', 'reservations', ['customer_id', 'listing_id'], unique=True, postgresql_where=sa.text("status = 'reserved'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_reservations_one_active_per_listing', table_name='reservations', postgresql_where=sa.text("status = 'reserved'"))
    op.drop_index(op.f('ix_reservations_status'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_provider_id'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_listing_id'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_customer_id'), table_name='reservations')
    op.drop_table('reservations')
    op.drop_table('provider_members')
    op.drop_index('ix_listings_status_pickup_end', table_name='listings')
    op.drop_index(op.f('ix_listings_provider_id'), table_name='listings')
    op.drop_index(op.f('ix_listings_price_paise'), table_name='listings')
    op.drop_index(op.f('ix_listings_meal_type'), table_name='listings')
    op.drop_table('listings')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_index(op.f('ix_providers_status'), table_name='providers')
    op.drop_table('providers')
    op.drop_index('ix_audit_log_entity', table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_created_at'), table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_table('users')
