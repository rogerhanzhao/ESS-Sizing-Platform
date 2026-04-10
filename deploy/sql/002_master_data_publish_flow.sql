BEGIN;

ALTER TABLE battery_cell_revisions
    ADD CONSTRAINT chk_battery_cell_revisions_publish_fields_pair
        CHECK (
            (published_dictionary_version_id IS NULL AND published_at IS NULL)
            OR
            (published_dictionary_version_id IS NOT NULL AND published_at IS NOT NULL)
        ),
    ADD CONSTRAINT chk_battery_cell_revisions_published_requires_dictionary
        CHECK (
            revision_status <> 'published'
            OR published_dictionary_version_id IS NOT NULL
        ),
    ADD CONSTRAINT chk_battery_cell_revisions_published_fields_require_status
        CHECK (
            published_dictionary_version_id IS NULL
            OR revision_status IN ('published', 'archived')
        );

ALTER TABLE dc_block_revisions
    ADD CONSTRAINT chk_dc_block_revisions_publish_fields_pair
        CHECK (
            (published_dictionary_version_id IS NULL AND published_at IS NULL)
            OR
            (published_dictionary_version_id IS NOT NULL AND published_at IS NOT NULL)
        ),
    ADD CONSTRAINT chk_dc_block_revisions_published_requires_dictionary
        CHECK (
            revision_status <> 'published'
            OR published_dictionary_version_id IS NOT NULL
        ),
    ADD CONSTRAINT chk_dc_block_revisions_published_fields_require_status
        CHECK (
            published_dictionary_version_id IS NULL
            OR revision_status IN ('published', 'archived')
        );

CREATE TABLE master_publish_batches (
    publish_batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_code varchar(16) NOT NULL,
    version_label varchar(64) NOT NULL,
    batch_status varchar(24) NOT NULL DEFAULT 'draft',
    summary text,
    requested_by varchar(64),
    approved_by varchar(64),
    published_by varchar(64),
    requested_at timestamptz NOT NULL DEFAULT NOW(),
    approved_at timestamptz,
    published_at timestamptz,
    dictionary_version_id uuid
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE SET NULL,
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_master_publish_batches_version UNIQUE (domain_code, version_label),
    CONSTRAINT uq_master_publish_batches_dictionary UNIQUE (dictionary_version_id),
    CONSTRAINT chk_master_publish_batches_domain
        CHECK (domain_code IN ('dc', 'ac')),
    CONSTRAINT chk_master_publish_batches_status
        CHECK (batch_status IN ('draft', 'review', 'approved', 'published', 'failed', 'archived')),
    CONSTRAINT chk_master_publish_batches_publish_time
        CHECK (
            batch_status <> 'published'
            OR (dictionary_version_id IS NOT NULL AND published_at IS NOT NULL)
        )
);

CREATE TABLE master_publish_batch_items (
    publish_batch_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publish_batch_id uuid NOT NULL
        REFERENCES master_publish_batches(publish_batch_id) ON DELETE CASCADE,
    entity_type varchar(32) NOT NULL,
    cell_revision_id uuid
        REFERENCES battery_cell_revisions(cell_revision_id) ON DELETE RESTRICT,
    dc_block_revision_id uuid
        REFERENCES dc_block_revisions(dc_block_revision_id) ON DELETE RESTRICT,
    item_status varchar(24) NOT NULL DEFAULT 'pending',
    snapshot_hash varchar(64),
    snapshot_payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_master_publish_batch_items_entity
        CHECK (entity_type IN ('battery_cell', 'dc_block')),
    CONSTRAINT chk_master_publish_batch_items_status
        CHECK (item_status IN ('pending', 'published', 'skipped', 'failed')),
    CONSTRAINT chk_master_publish_batch_items_shape
        CHECK (
            (entity_type = 'battery_cell' AND cell_revision_id IS NOT NULL AND dc_block_revision_id IS NULL)
            OR
            (entity_type = 'dc_block' AND dc_block_revision_id IS NOT NULL AND cell_revision_id IS NULL)
        )
);

CREATE UNIQUE INDEX uq_master_publish_batch_items_cell_revision
    ON master_publish_batch_items (publish_batch_id, cell_revision_id)
    WHERE cell_revision_id IS NOT NULL;

CREATE UNIQUE INDEX uq_master_publish_batch_items_dc_block_revision
    ON master_publish_batch_items (publish_batch_id, dc_block_revision_id)
    WHERE dc_block_revision_id IS NOT NULL;

CREATE INDEX idx_master_publish_batches_status_requested_at
    ON master_publish_batches (batch_status, requested_at DESC);

CREATE INDEX idx_master_publish_batches_domain_status
    ON master_publish_batches (domain_code, batch_status, created_at DESC);

CREATE INDEX idx_master_publish_batch_items_batch_status
    ON master_publish_batch_items (publish_batch_id, item_status);

CREATE INDEX idx_battery_cell_revisions_published_dictionary
    ON battery_cell_revisions (published_dictionary_version_id)
    WHERE published_dictionary_version_id IS NOT NULL;

CREATE INDEX idx_dc_block_revisions_published_dictionary
    ON dc_block_revisions (published_dictionary_version_id)
    WHERE published_dictionary_version_id IS NOT NULL;

CREATE VIEW vw_battery_cell_latest_revision AS
SELECT
    m.cell_master_id,
    m.cell_code,
    m.cell_model,
    m.vendor_name,
    m.chemistry_code,
    m.record_status,
    r.cell_revision_id,
    r.revision_no,
    r.revision_status,
    r.source_type,
    r.nominal_capacity_ah,
    r.nominal_voltage_v,
    r.nominal_energy_wh,
    r.published_dictionary_version_id,
    r.published_at,
    r.updated_at AS revision_updated_at
FROM battery_cell_masters m
LEFT JOIN LATERAL (
    SELECT r1.*
    FROM battery_cell_revisions r1
    WHERE r1.cell_master_id = m.cell_master_id
    ORDER BY r1.revision_no DESC
    LIMIT 1
) r ON TRUE;

CREATE VIEW vw_dc_block_latest_revision AS
SELECT
    m.dc_block_master_id,
    m.block_code,
    m.block_name,
    m.block_form,
    m.vendor_name,
    m.enclosure_type,
    m.record_status,
    r.dc_block_revision_id,
    r.revision_no,
    r.revision_status,
    r.source_type,
    r.block_nameplate_capacity_mwh,
    r.nominal_voltage_v,
    r.charge_power_limit_mw,
    r.discharge_power_limit_mw,
    r.published_dictionary_version_id,
    r.published_at,
    r.updated_at AS revision_updated_at
FROM dc_block_masters m
LEFT JOIN LATERAL (
    SELECT r1.*
    FROM dc_block_revisions r1
    WHERE r1.dc_block_master_id = m.dc_block_master_id
    ORDER BY r1.revision_no DESC
    LIMIT 1
) r ON TRUE;

CREATE VIEW vw_battery_cell_published_snapshot AS
SELECT
    m.cell_master_id,
    m.cell_code,
    r.cell_revision_id,
    r.revision_no,
    r.published_dictionary_version_id,
    dv.version_label,
    dv.is_active AS dictionary_is_active,
    t.cell_type_id,
    t.source_cell_type_id,
    t.cell_model AS snapshot_cell_model,
    t.cell_capacity_ah,
    t.cell_nominal_voltage_v,
    t.cell_energy_wh
FROM battery_cell_masters m
JOIN battery_cell_revisions r
    ON r.cell_master_id = m.cell_master_id
   AND r.published_dictionary_version_id IS NOT NULL
LEFT JOIN dictionary_versions dv
    ON dv.dictionary_version_id = r.published_dictionary_version_id
LEFT JOIN battery_cell_types t
    ON t.source_cell_revision_id = r.cell_revision_id;

CREATE VIEW vw_dc_block_published_snapshot AS
SELECT
    m.dc_block_master_id,
    m.block_code,
    r.dc_block_revision_id,
    r.revision_no,
    r.published_dictionary_version_id,
    dv.version_label,
    dv.is_active AS dictionary_is_active,
    t.dc_block_template_id,
    t.source_dc_block_code,
    t.source_dc_block_name,
    t.block_form,
    t.block_nameplate_capacity_mwh
FROM dc_block_masters m
JOIN dc_block_revisions r
    ON r.dc_block_master_id = m.dc_block_master_id
   AND r.published_dictionary_version_id IS NOT NULL
LEFT JOIN dictionary_versions dv
    ON dv.dictionary_version_id = r.published_dictionary_version_id
LEFT JOIN dc_block_templates t
    ON t.source_dc_block_revision_id = r.dc_block_revision_id;

CREATE VIEW vw_master_publish_batch_summary AS
SELECT
    b.publish_batch_id,
    b.domain_code,
    b.version_label,
    b.batch_status,
    b.dictionary_version_id,
    b.requested_by,
    b.approved_by,
    b.published_by,
    b.requested_at,
    b.approved_at,
    b.published_at,
    COUNT(i.publish_batch_item_id) AS total_items,
    COUNT(*) FILTER (WHERE i.item_status = 'pending') AS pending_items,
    COUNT(*) FILTER (WHERE i.item_status = 'published') AS published_items,
    COUNT(*) FILTER (WHERE i.item_status = 'skipped') AS skipped_items,
    COUNT(*) FILTER (WHERE i.item_status = 'failed') AS failed_items
FROM master_publish_batches b
LEFT JOIN master_publish_batch_items i
    ON i.publish_batch_id = b.publish_batch_id
GROUP BY
    b.publish_batch_id,
    b.domain_code,
    b.version_label,
    b.batch_status,
    b.dictionary_version_id,
    b.requested_by,
    b.approved_by,
    b.published_by,
    b.requested_at,
    b.approved_at,
    b.published_at;

CREATE TRIGGER trg_master_publish_batches_set_updated_at
    BEFORE UPDATE ON master_publish_batches
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_master_publish_batch_items_set_updated_at
    BEFORE UPDATE ON master_publish_batch_items
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

COMMIT;
