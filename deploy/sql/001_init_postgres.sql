BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Project and working state
-- ---------------------------------------------------------------------------

CREATE TABLE projects (
    project_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code varchar(64) NOT NULL UNIQUE,
    project_name varchar(255) NOT NULL,
    project_status varchar(24) NOT NULL DEFAULT 'active',
    description text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_projects_status
        CHECK (project_status IN ('active', 'archived')),
    CONSTRAINT chk_projects_code_nonempty
        CHECK (btrim(project_code) <> ''),
    CONSTRAINT chk_projects_name_nonempty
        CHECK (btrim(project_name) <> '')
);

CREATE TABLE project_stage_drafts (
    draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    stage_code varchar(24) NOT NULL,
    draft_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    ui_version varchar(32),
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_stage_drafts UNIQUE (project_id, stage_code),
    CONSTRAINT chk_project_stage_drafts_stage
        CHECK (stage_code IN ('dc', 'ac', 'sld', 'layout', 'report'))
);

-- ---------------------------------------------------------------------------
-- Dictionary versions and master data
-- ---------------------------------------------------------------------------

CREATE TABLE dictionary_versions (
    dictionary_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_code varchar(16) NOT NULL,
    version_label varchar(64) NOT NULL,
    source_file_name varchar(255) NOT NULL,
    source_file_sha256 varchar(64) NOT NULL,
    is_active boolean NOT NULL DEFAULT FALSE,
    loaded_at timestamptz NOT NULL DEFAULT NOW(),
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_dictionary_versions_source UNIQUE (domain_code, source_file_sha256),
    CONSTRAINT chk_dictionary_versions_domain
        CHECK (domain_code IN ('dc', 'ac'))
);

CREATE TABLE battery_cell_masters (
    cell_master_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cell_code varchar(64) NOT NULL UNIQUE,
    cell_model varchar(128) NOT NULL,
    vendor_name varchar(128),
    chemistry_code varchar(32),
    record_status varchar(24) NOT NULL DEFAULT 'active',
    remarks text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_battery_cell_masters_status
        CHECK (record_status IN ('active', 'inactive', 'archived')),
    CONSTRAINT chk_battery_cell_masters_code_nonempty
        CHECK (btrim(cell_code) <> ''),
    CONSTRAINT chk_battery_cell_masters_model_nonempty
        CHECK (btrim(cell_model) <> '')
);

CREATE TABLE battery_cell_revisions (
    cell_revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cell_master_id uuid NOT NULL
        REFERENCES battery_cell_masters(cell_master_id) ON DELETE CASCADE,
    revision_no integer NOT NULL,
    revision_status varchar(24) NOT NULL DEFAULT 'draft',
    source_type varchar(24) NOT NULL DEFAULT 'manual',
    published_dictionary_version_id uuid
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE SET NULL,
    nominal_capacity_ah numeric(16, 6) NOT NULL,
    nominal_voltage_v numeric(16, 6) NOT NULL,
    min_voltage_v numeric(16, 6),
    max_voltage_v numeric(16, 6),
    nominal_energy_wh numeric(16, 6),
    dc_internal_resistance_mohm numeric(16, 6),
    mass_kg numeric(16, 6),
    cycle_life_nominal integer,
    parameter_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    published_at timestamptz,
    CONSTRAINT uq_battery_cell_revisions UNIQUE (cell_master_id, revision_no),
    CONSTRAINT chk_battery_cell_revisions_status
        CHECK (revision_status IN ('draft', 'published', 'archived')),
    CONSTRAINT chk_battery_cell_revisions_source_type
        CHECK (source_type IN ('manual', 'imported')),
    CONSTRAINT chk_battery_cell_revisions_revision_no
        CHECK (revision_no > 0),
    CONSTRAINT chk_battery_cell_revisions_capacity
        CHECK (nominal_capacity_ah > 0),
    CONSTRAINT chk_battery_cell_revisions_nominal_voltage
        CHECK (nominal_voltage_v > 0),
    CONSTRAINT chk_battery_cell_revisions_cycle_life
        CHECK (cycle_life_nominal IS NULL OR cycle_life_nominal >= 0)
);

CREATE TABLE dc_block_masters (
    dc_block_master_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    block_code varchar(64) NOT NULL UNIQUE,
    block_name varchar(255) NOT NULL,
    block_form varchar(24) NOT NULL,
    vendor_name varchar(128),
    enclosure_type varchar(32),
    record_status varchar(24) NOT NULL DEFAULT 'active',
    remarks text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_dc_block_masters_form
        CHECK (block_form IN ('container', 'cabinet')),
    CONSTRAINT chk_dc_block_masters_status
        CHECK (record_status IN ('active', 'inactive', 'archived')),
    CONSTRAINT chk_dc_block_masters_code_nonempty
        CHECK (btrim(block_code) <> ''),
    CONSTRAINT chk_dc_block_masters_name_nonempty
        CHECK (btrim(block_name) <> '')
);

CREATE TABLE dc_block_revisions (
    dc_block_revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dc_block_master_id uuid NOT NULL
        REFERENCES dc_block_masters(dc_block_master_id) ON DELETE CASCADE,
    revision_no integer NOT NULL,
    revision_status varchar(24) NOT NULL DEFAULT 'draft',
    source_type varchar(24) NOT NULL DEFAULT 'manual',
    published_dictionary_version_id uuid
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE SET NULL,
    racks_per_block integer,
    packs_per_rack integer,
    block_nameplate_capacity_mwh numeric(16, 6) NOT NULL,
    nominal_voltage_v numeric(16, 6),
    operating_voltage_min_v numeric(16, 6),
    operating_voltage_max_v numeric(16, 6),
    charge_power_limit_mw numeric(16, 6),
    discharge_power_limit_mw numeric(16, 6),
    auxiliary_power_kw numeric(16, 6),
    enclosure_size_ft integer,
    footprint_length_m numeric(16, 6),
    footprint_width_m numeric(16, 6),
    footprint_height_m numeric(16, 6),
    parameter_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    published_at timestamptz,
    CONSTRAINT uq_dc_block_revisions UNIQUE (dc_block_master_id, revision_no),
    CONSTRAINT chk_dc_block_revisions_status
        CHECK (revision_status IN ('draft', 'published', 'archived')),
    CONSTRAINT chk_dc_block_revisions_source_type
        CHECK (source_type IN ('manual', 'imported')),
    CONSTRAINT chk_dc_block_revisions_revision_no
        CHECK (revision_no > 0),
    CONSTRAINT chk_dc_block_revisions_racks_per_block
        CHECK (racks_per_block IS NULL OR racks_per_block > 0),
    CONSTRAINT chk_dc_block_revisions_packs_per_rack
        CHECK (packs_per_rack IS NULL OR packs_per_rack > 0),
    CONSTRAINT chk_dc_block_revisions_nameplate
        CHECK (block_nameplate_capacity_mwh > 0),
    CONSTRAINT chk_dc_block_revisions_enclosure_size
        CHECK (enclosure_size_ft IS NULL OR enclosure_size_ft IN (20, 40))
);

CREATE TABLE battery_cell_types (
    cell_type_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dictionary_version_id uuid NOT NULL
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE CASCADE,
    source_cell_master_id uuid
        REFERENCES battery_cell_masters(cell_master_id) ON DELETE SET NULL,
    source_cell_revision_id uuid
        REFERENCES battery_cell_revisions(cell_revision_id) ON DELETE SET NULL,
    source_cell_type_id integer NOT NULL,
    cell_model varchar(128),
    cell_capacity_ah numeric(16, 6),
    cell_nominal_voltage_v numeric(16, 6),
    cell_energy_wh numeric(16, 6),
    raw_row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_battery_cell_types_source UNIQUE (dictionary_version_id, source_cell_type_id)
);

CREATE TABLE pack_types (
    pack_type_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dictionary_version_id uuid NOT NULL
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE CASCADE,
    source_pack_type_id integer NOT NULL,
    source_cell_type_id integer NOT NULL,
    cells_in_series integer,
    cells_in_parallel integer,
    pack_nominal_voltage_v numeric(16, 6),
    raw_row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_pack_types_source UNIQUE (dictionary_version_id, source_pack_type_id),
    CONSTRAINT fk_pack_types_source_cell
        FOREIGN KEY (dictionary_version_id, source_cell_type_id)
        REFERENCES battery_cell_types(dictionary_version_id, source_cell_type_id),
    CONSTRAINT chk_pack_types_series
        CHECK (cells_in_series IS NULL OR cells_in_series > 0),
    CONSTRAINT chk_pack_types_parallel
        CHECK (cells_in_parallel IS NULL OR cells_in_parallel > 0)
);

CREATE TABLE rack_types (
    rack_type_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dictionary_version_id uuid NOT NULL
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE CASCADE,
    source_rack_type_id integer NOT NULL,
    source_pack_type_id integer NOT NULL,
    packs_per_rack integer,
    raw_row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_rack_types_source UNIQUE (dictionary_version_id, source_rack_type_id),
    CONSTRAINT fk_rack_types_source_pack
        FOREIGN KEY (dictionary_version_id, source_pack_type_id)
        REFERENCES pack_types(dictionary_version_id, source_pack_type_id),
    CONSTRAINT chk_rack_types_packs_per_rack
        CHECK (packs_per_rack IS NULL OR packs_per_rack > 0)
);

CREATE TABLE dc_block_templates (
    dc_block_template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dictionary_version_id uuid NOT NULL
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE CASCADE,
    source_dc_block_master_id uuid
        REFERENCES dc_block_masters(dc_block_master_id) ON DELETE SET NULL,
    source_dc_block_revision_id uuid
        REFERENCES dc_block_revisions(dc_block_revision_id) ON DELETE SET NULL,
    source_dc_block_code varchar(128) NOT NULL,
    source_dc_block_name varchar(255) NOT NULL,
    block_form varchar(24) NOT NULL,
    source_rack_type_id integer,
    racks_per_block integer,
    block_nameplate_capacity_mwh numeric(16, 6),
    is_active boolean NOT NULL DEFAULT TRUE,
    is_default_option boolean NOT NULL DEFAULT FALSE,
    raw_row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_dc_block_templates_source UNIQUE (dictionary_version_id, source_dc_block_code),
    CONSTRAINT fk_dc_block_templates_source_rack
        FOREIGN KEY (dictionary_version_id, source_rack_type_id)
        REFERENCES rack_types(dictionary_version_id, source_rack_type_id),
    CONSTRAINT chk_dc_block_templates_form
        CHECK (block_form IN ('container', 'cabinet')),
    CONSTRAINT chk_dc_block_templates_racks_per_block
        CHECK (racks_per_block IS NULL OR racks_per_block > 0)
);

CREATE TABLE soh_profiles (
    soh_profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dictionary_version_id uuid NOT NULL
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE CASCADE,
    source_profile_id integer NOT NULL,
    c_rate numeric(16, 6) NOT NULL,
    cycles_per_year integer NOT NULL,
    raw_row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_soh_profiles_source UNIQUE (dictionary_version_id, source_profile_id),
    CONSTRAINT chk_soh_profiles_c_rate CHECK (c_rate > 0),
    CONSTRAINT chk_soh_profiles_cycles_per_year CHECK (cycles_per_year >= 0)
);

CREATE TABLE soh_curve_points (
    soh_curve_point_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    soh_profile_id uuid NOT NULL REFERENCES soh_profiles(soh_profile_id) ON DELETE CASCADE,
    life_year_index integer NOT NULL,
    soh_dc_pct numeric(16, 6) NOT NULL,
    raw_row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_soh_curve_points UNIQUE (soh_profile_id, life_year_index),
    CONSTRAINT chk_soh_curve_points_year CHECK (life_year_index >= 0)
);

CREATE TABLE rte_profiles (
    rte_profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dictionary_version_id uuid NOT NULL
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE CASCADE,
    source_profile_id integer NOT NULL,
    c_rate numeric(16, 6) NOT NULL,
    raw_row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_rte_profiles_source UNIQUE (dictionary_version_id, source_profile_id),
    CONSTRAINT chk_rte_profiles_c_rate CHECK (c_rate > 0)
);

CREATE TABLE rte_curve_points (
    rte_curve_point_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rte_profile_id uuid NOT NULL REFERENCES rte_profiles(rte_profile_id) ON DELETE CASCADE,
    soh_band_min_pct numeric(16, 6) NOT NULL,
    rte_dc_pct numeric(16, 6) NOT NULL,
    raw_row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_rte_curve_points UNIQUE (rte_profile_id, soh_band_min_pct)
);

CREATE TABLE ac_block_templates (
    ac_block_template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dictionary_version_id uuid NOT NULL
        REFERENCES dictionary_versions(dictionary_version_id) ON DELETE CASCADE,
    template_code varchar(128) NOT NULL,
    pcs_per_block integer NOT NULL,
    pcs_rating_kw numeric(16, 6) NOT NULL,
    feeders_per_block integer NOT NULL,
    transformer_rating_kva numeric(16, 6),
    mv_voltage_kv numeric(16, 6),
    lv_voltage_v numeric(16, 6),
    grid_power_factor numeric(16, 6),
    is_active boolean NOT NULL DEFAULT TRUE,
    raw_row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_ac_block_templates_code UNIQUE (dictionary_version_id, template_code),
    CONSTRAINT chk_ac_block_templates_pcs_per_block CHECK (pcs_per_block > 0),
    CONSTRAINT chk_ac_block_templates_feeders_per_block CHECK (feeders_per_block > 0),
    CONSTRAINT chk_ac_block_templates_pcs_rating CHECK (pcs_rating_kw > 0)
);

-- ---------------------------------------------------------------------------
-- DC runs
-- ---------------------------------------------------------------------------

CREATE TABLE dc_runs (
    dc_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    dc_dictionary_version_id uuid NOT NULL
        REFERENCES dictionary_versions(dictionary_version_id),
    project_name_snapshot varchar(255) NOT NULL,
    input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    stage1_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    poi_power_req_mw numeric(16, 6) NOT NULL,
    poi_energy_req_mwh numeric(16, 6) NOT NULL,
    poi_nominal_voltage_kv numeric(16, 6),
    poi_frequency_hz numeric(16, 6),
    project_life_years integer NOT NULL,
    cycles_per_year integer NOT NULL,
    poi_guarantee_year integer NOT NULL,
    eff_dc_to_poi_frac numeric(16, 6) NOT NULL,
    dc_energy_capacity_required_mwh numeric(16, 6) NOT NULL,
    dc_power_required_mw numeric(16, 6) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'succeeded',
    error_message text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_dc_runs_status
        CHECK (status IN ('draft', 'running', 'succeeded', 'failed', 'archived')),
    CONSTRAINT chk_dc_runs_life_years CHECK (project_life_years > 0),
    CONSTRAINT chk_dc_runs_cycles_per_year CHECK (cycles_per_year >= 0),
    CONSTRAINT chk_dc_runs_guarantee_year CHECK (
        poi_guarantee_year >= 0 AND poi_guarantee_year <= project_life_years
    ),
    CONSTRAINT chk_dc_runs_poi_power CHECK (poi_power_req_mw >= 0),
    CONSTRAINT chk_dc_runs_poi_energy CHECK (poi_energy_req_mwh >= 0),
    CONSTRAINT chk_dc_runs_dc_energy_required CHECK (dc_energy_capacity_required_mwh >= 0),
    CONSTRAINT chk_dc_runs_dc_power_required CHECK (dc_power_required_mw >= 0)
);

CREATE TABLE dc_scenarios (
    dc_scenario_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dc_run_id uuid NOT NULL REFERENCES dc_runs(dc_run_id) ON DELETE CASCADE,
    scenario_code varchar(32) NOT NULL,
    display_order integer NOT NULL,
    is_active_selected boolean NOT NULL DEFAULT FALSE,
    converged boolean NOT NULL DEFAULT FALSE,
    iteration_count integer NOT NULL,
    container_count integer NOT NULL DEFAULT 0,
    cabinet_count integer NOT NULL DEFAULT 0,
    busbars_needed integer NOT NULL DEFAULT 0,
    dc_nameplate_bol_mwh numeric(16, 6) NOT NULL,
    oversize_mwh numeric(16, 6) NOT NULL DEFAULT 0,
    config_adjustment_frac numeric(16, 6) NOT NULL DEFAULT 0,
    poi_usable_energy_mwh_at_guarantee_year numeric(16, 6),
    stage2_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    stage3_meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dc_scenarios_code UNIQUE (dc_run_id, scenario_code),
    CONSTRAINT uq_dc_scenarios_lineage UNIQUE (dc_run_id, dc_scenario_id),
    CONSTRAINT chk_dc_scenarios_display_order CHECK (display_order >= 0),
    CONSTRAINT chk_dc_scenarios_iteration_count CHECK (iteration_count >= 0),
    CONSTRAINT chk_dc_scenarios_container_count CHECK (container_count >= 0),
    CONSTRAINT chk_dc_scenarios_cabinet_count CHECK (cabinet_count >= 0),
    CONSTRAINT chk_dc_scenarios_busbars_needed CHECK (busbars_needed >= 0),
    CONSTRAINT chk_dc_scenarios_nameplate CHECK (dc_nameplate_bol_mwh >= 0),
    CONSTRAINT chk_dc_scenarios_oversize CHECK (oversize_mwh >= 0)
);

CREATE TABLE dc_scenario_items (
    dc_scenario_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dc_scenario_id uuid NOT NULL REFERENCES dc_scenarios(dc_scenario_id) ON DELETE CASCADE,
    line_no integer NOT NULL,
    block_code varchar(128) NOT NULL,
    block_name varchar(255) NOT NULL,
    block_form varchar(24) NOT NULL,
    unit_capacity_mwh numeric(16, 6) NOT NULL,
    quantity integer NOT NULL,
    subtotal_mwh numeric(16, 6) NOT NULL,
    CONSTRAINT uq_dc_scenario_items_line UNIQUE (dc_scenario_id, line_no),
    CONSTRAINT chk_dc_scenario_items_line_no CHECK (line_no > 0),
    CONSTRAINT chk_dc_scenario_items_form
        CHECK (block_form IN ('container', 'cabinet')),
    CONSTRAINT chk_dc_scenario_items_unit_capacity CHECK (unit_capacity_mwh >= 0),
    CONSTRAINT chk_dc_scenario_items_quantity CHECK (quantity > 0),
    CONSTRAINT chk_dc_scenario_items_subtotal CHECK (subtotal_mwh >= 0)
);

CREATE TABLE dc_scenario_yearly_results (
    dc_year_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dc_scenario_id uuid NOT NULL REFERENCES dc_scenarios(dc_scenario_id) ON DELETE CASCADE,
    year_index integer NOT NULL,
    soh_relative numeric(16, 6) NOT NULL,
    soh_absolute numeric(16, 6) NOT NULL,
    dc_nameplate_bol_mwh numeric(16, 6) NOT NULL,
    dc_gross_capacity_mwh numeric(16, 6) NOT NULL,
    dc_usable_mwh numeric(16, 6) NOT NULL,
    dc_rte_frac numeric(16, 6) NOT NULL,
    system_rte_frac numeric(16, 6) NOT NULL,
    poi_usable_energy_mwh numeric(16, 6) NOT NULL,
    meets_poi_req boolean NOT NULL,
    is_guarantee_year boolean NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_dc_scenario_yearly_results UNIQUE (dc_scenario_id, year_index),
    CONSTRAINT chk_dc_scenario_yearly_year CHECK (year_index >= 0),
    CONSTRAINT chk_dc_scenario_yearly_nameplate CHECK (dc_nameplate_bol_mwh >= 0),
    CONSTRAINT chk_dc_scenario_yearly_gross CHECK (dc_gross_capacity_mwh >= 0),
    CONSTRAINT chk_dc_scenario_yearly_usable CHECK (dc_usable_mwh >= 0),
    CONSTRAINT chk_dc_scenario_yearly_poi_usable CHECK (poi_usable_energy_mwh >= 0)
);

-- ---------------------------------------------------------------------------
-- AC runs
-- ---------------------------------------------------------------------------

CREATE TABLE ac_runs (
    ac_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    source_dc_run_id uuid NOT NULL,
    source_dc_scenario_id uuid NOT NULL,
    ac_dictionary_version_id uuid REFERENCES dictionary_versions(dictionary_version_id),
    selected_ratio varchar(16) NOT NULL,
    input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    options_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    num_blocks integer NOT NULL,
    pcs_per_block integer NOT NULL,
    pcs_rating_kw numeric(16, 6) NOT NULL,
    pcs_count_total integer NOT NULL,
    block_size_mw numeric(16, 6) NOT NULL,
    total_ac_mw numeric(16, 6) NOT NULL,
    overhead_mw numeric(16, 6) NOT NULL DEFAULT 0,
    dc_blocks_total integer NOT NULL,
    dc_total_mwh numeric(16, 6) NOT NULL,
    mv_voltage_kv numeric(16, 6),
    lv_voltage_v numeric(16, 6),
    transformer_count integer NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'succeeded',
    error_message text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ac_runs_lineage UNIQUE (ac_run_id, source_dc_run_id, source_dc_scenario_id),
    CONSTRAINT fk_ac_runs_dc_lineage
        FOREIGN KEY (source_dc_run_id, source_dc_scenario_id)
        REFERENCES dc_scenarios(dc_run_id, dc_scenario_id),
    CONSTRAINT chk_ac_runs_ratio_format
        CHECK (selected_ratio ~ '^[0-9]+:[0-9]+$'),
    CONSTRAINT chk_ac_runs_status
        CHECK (status IN ('draft', 'running', 'succeeded', 'failed', 'archived')),
    CONSTRAINT chk_ac_runs_num_blocks CHECK (num_blocks > 0),
    CONSTRAINT chk_ac_runs_pcs_per_block CHECK (pcs_per_block > 0),
    CONSTRAINT chk_ac_runs_pcs_rating CHECK (pcs_rating_kw > 0),
    CONSTRAINT chk_ac_runs_pcs_count_total CHECK (pcs_count_total > 0),
    CONSTRAINT chk_ac_runs_block_size CHECK (block_size_mw >= 0),
    CONSTRAINT chk_ac_runs_total_ac CHECK (total_ac_mw >= 0),
    CONSTRAINT chk_ac_runs_dc_blocks_total CHECK (dc_blocks_total >= 0),
    CONSTRAINT chk_ac_runs_dc_total_mwh CHECK (dc_total_mwh >= 0),
    CONSTRAINT chk_ac_runs_transformer_count CHECK (transformer_count >= 0)
);

CREATE TABLE ac_blocks (
    ac_block_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ac_run_id uuid NOT NULL REFERENCES ac_runs(ac_run_id) ON DELETE CASCADE,
    block_index integer NOT NULL,
    dc_blocks_total integer NOT NULL,
    pcs_count integer NOT NULL,
    block_size_mw numeric(16, 6) NOT NULL,
    container_size_ft integer,
    transformer_rating_kva numeric(16, 6),
    CONSTRAINT uq_ac_blocks_index UNIQUE (ac_run_id, block_index),
    CONSTRAINT chk_ac_blocks_index CHECK (block_index > 0),
    CONSTRAINT chk_ac_blocks_dc_blocks_total CHECK (dc_blocks_total >= 0),
    CONSTRAINT chk_ac_blocks_pcs_count CHECK (pcs_count > 0),
    CONSTRAINT chk_ac_blocks_block_size CHECK (block_size_mw >= 0),
    CONSTRAINT chk_ac_blocks_container_size CHECK (
        container_size_ft IS NULL OR container_size_ft IN (20, 40)
    )
);

CREATE TABLE ac_feeders (
    ac_feeder_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ac_block_id uuid NOT NULL REFERENCES ac_blocks(ac_block_id) ON DELETE CASCADE,
    feeder_index integer NOT NULL,
    pcs_id_label varchar(64),
    dc_block_count integer NOT NULL,
    pcs_rating_kw numeric(16, 6),
    CONSTRAINT uq_ac_feeders_index UNIQUE (ac_block_id, feeder_index),
    CONSTRAINT chk_ac_feeders_index CHECK (feeder_index > 0),
    CONSTRAINT chk_ac_feeders_dc_block_count CHECK (dc_block_count >= 0)
);

-- ---------------------------------------------------------------------------
-- Artifacts and generated runs
-- ---------------------------------------------------------------------------

CREATE TABLE artifacts (
    artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    artifact_role varchar(32) NOT NULL,
    file_name varchar(255) NOT NULL,
    mime_type varchar(128) NOT NULL,
    storage_backend varchar(32) NOT NULL,
    storage_path text NOT NULL,
    sha256 varchar(64) NOT NULL,
    size_bytes bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_artifacts_project_role_sha UNIQUE (project_id, artifact_role, sha256),
    CONSTRAINT chk_artifacts_file_name_nonempty CHECK (btrim(file_name) <> ''),
    CONSTRAINT chk_artifacts_storage_backend_nonempty CHECK (btrim(storage_backend) <> ''),
    CONSTRAINT chk_artifacts_size_bytes CHECK (size_bytes >= 0)
);

CREATE TABLE sld_runs (
    sld_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    source_dc_run_id uuid NOT NULL,
    source_dc_scenario_id uuid NOT NULL,
    source_ac_run_id uuid NOT NULL,
    group_index integer NOT NULL,
    scenario_code varchar(32) NOT NULL,
    input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    spec_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    snapshot_hash varchar(64) NOT NULL,
    svg_artifact_id uuid REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    png_artifact_id uuid REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    snapshot_artifact_id uuid REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    status varchar(24) NOT NULL DEFAULT 'succeeded',
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_sld_runs_dc_lineage
        FOREIGN KEY (source_dc_run_id, source_dc_scenario_id)
        REFERENCES dc_scenarios(dc_run_id, dc_scenario_id),
    CONSTRAINT fk_sld_runs_ac_lineage
        FOREIGN KEY (source_ac_run_id, source_dc_run_id, source_dc_scenario_id)
        REFERENCES ac_runs(ac_run_id, source_dc_run_id, source_dc_scenario_id),
    CONSTRAINT chk_sld_runs_group_index CHECK (group_index > 0),
    CONSTRAINT chk_sld_runs_status
        CHECK (status IN ('draft', 'running', 'succeeded', 'failed', 'archived'))
);

CREATE TABLE layout_runs (
    layout_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    source_dc_run_id uuid NOT NULL,
    source_dc_scenario_id uuid NOT NULL,
    source_ac_run_id uuid NOT NULL,
    block_index integer NOT NULL,
    arrangement_code varchar(24) NOT NULL,
    input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    spec_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    svg_artifact_id uuid REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    png_artifact_id uuid REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    spec_artifact_id uuid REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    status varchar(24) NOT NULL DEFAULT 'succeeded',
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_layout_runs_dc_lineage
        FOREIGN KEY (source_dc_run_id, source_dc_scenario_id)
        REFERENCES dc_scenarios(dc_run_id, dc_scenario_id),
    CONSTRAINT fk_layout_runs_ac_lineage
        FOREIGN KEY (source_ac_run_id, source_dc_run_id, source_dc_scenario_id)
        REFERENCES ac_runs(ac_run_id, source_dc_run_id, source_dc_scenario_id),
    CONSTRAINT chk_layout_runs_block_index CHECK (block_index > 0),
    CONSTRAINT chk_layout_runs_status
        CHECK (status IN ('draft', 'running', 'succeeded', 'failed', 'archived'))
);

CREATE TABLE report_runs (
    report_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    source_dc_run_id uuid NOT NULL,
    source_dc_scenario_id uuid NOT NULL,
    source_ac_run_id uuid NOT NULL,
    source_sld_run_id uuid REFERENCES sld_runs(sld_run_id) ON DELETE SET NULL,
    source_layout_run_id uuid REFERENCES layout_runs(layout_run_id) ON DELETE SET NULL,
    report_template_code varchar(32) NOT NULL,
    brand_code varchar(32),
    context_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    qc_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    docx_artifact_id uuid REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    status varchar(24) NOT NULL DEFAULT 'succeeded',
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_report_runs_dc_lineage
        FOREIGN KEY (source_dc_run_id, source_dc_scenario_id)
        REFERENCES dc_scenarios(dc_run_id, dc_scenario_id),
    CONSTRAINT fk_report_runs_ac_lineage
        FOREIGN KEY (source_ac_run_id, source_dc_run_id, source_dc_scenario_id)
        REFERENCES ac_runs(ac_run_id, source_dc_run_id, source_dc_scenario_id),
    CONSTRAINT chk_report_runs_status
        CHECK (status IN ('draft', 'running', 'succeeded', 'failed', 'archived'))
);

CREATE TABLE project_stage_state (
    project_id uuid PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
    active_dc_run_id uuid REFERENCES dc_runs(dc_run_id) ON DELETE SET NULL,
    active_dc_scenario_id uuid REFERENCES dc_scenarios(dc_scenario_id) ON DELETE SET NULL,
    active_ac_run_id uuid REFERENCES ac_runs(ac_run_id) ON DELETE SET NULL,
    active_sld_run_id uuid REFERENCES sld_runs(sld_run_id) ON DELETE SET NULL,
    active_layout_run_id uuid REFERENCES layout_runs(layout_run_id) ON DELETE SET NULL,
    active_report_run_id uuid REFERENCES report_runs(report_run_id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX uq_dictionary_versions_one_active_per_domain
    ON dictionary_versions (domain_code)
    WHERE is_active;

CREATE UNIQUE INDEX uq_battery_cell_revisions_one_published
    ON battery_cell_revisions (cell_master_id)
    WHERE revision_status = 'published';

CREATE UNIQUE INDEX uq_dc_block_revisions_one_published
    ON dc_block_revisions (dc_block_master_id)
    WHERE revision_status = 'published';

CREATE UNIQUE INDEX uq_dc_scenarios_one_selected_per_run
    ON dc_scenarios (dc_run_id)
    WHERE is_active_selected;

CREATE INDEX idx_battery_cell_revisions_master_status
    ON battery_cell_revisions (cell_master_id, revision_status, revision_no DESC);

CREATE INDEX idx_dc_block_revisions_master_status
    ON dc_block_revisions (dc_block_master_id, revision_status, revision_no DESC);

CREATE INDEX idx_dc_runs_project_created_at
    ON dc_runs (project_id, created_at DESC);

CREATE INDEX idx_dc_scenarios_run_selected
    ON dc_scenarios (dc_run_id, is_active_selected);

CREATE INDEX idx_ac_runs_project_created_at
    ON ac_runs (project_id, created_at DESC);

CREATE INDEX idx_ac_runs_source_dc
    ON ac_runs (source_dc_run_id, source_dc_scenario_id);

CREATE INDEX idx_sld_runs_project_created_at
    ON sld_runs (project_id, created_at DESC);

CREATE INDEX idx_sld_runs_source_ac
    ON sld_runs (source_ac_run_id);

CREATE INDEX idx_layout_runs_project_created_at
    ON layout_runs (project_id, created_at DESC);

CREATE INDEX idx_layout_runs_source_ac
    ON layout_runs (source_ac_run_id);

CREATE INDEX idx_report_runs_project_created_at
    ON report_runs (project_id, created_at DESC);

CREATE INDEX idx_report_runs_source_ac
    ON report_runs (source_ac_run_id);

CREATE INDEX idx_artifacts_project_created_at
    ON artifacts (project_id, created_at DESC);

CREATE INDEX idx_artifacts_sha256
    ON artifacts (sha256);

CREATE INDEX idx_pack_types_source_cell
    ON pack_types (dictionary_version_id, source_cell_type_id);

CREATE INDEX idx_rack_types_source_pack
    ON rack_types (dictionary_version_id, source_pack_type_id);

CREATE INDEX idx_dc_block_templates_source_rack
    ON dc_block_templates (dictionary_version_id, source_rack_type_id);

-- Optional JSONB indexes after query patterns stabilize.
-- CREATE INDEX idx_project_stage_drafts_json ON project_stage_drafts USING GIN (draft_json);
-- CREATE INDEX idx_dc_runs_input_json ON dc_runs USING GIN (input_json);
-- CREATE INDEX idx_ac_runs_options_json ON ac_runs USING GIN (options_json);
-- CREATE INDEX idx_report_runs_context_json ON report_runs USING GIN (context_json);

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------

CREATE TRIGGER trg_projects_set_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_battery_cell_masters_set_updated_at
    BEFORE UPDATE ON battery_cell_masters
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_battery_cell_revisions_set_updated_at
    BEFORE UPDATE ON battery_cell_revisions
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_dc_block_masters_set_updated_at
    BEFORE UPDATE ON dc_block_masters
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_dc_block_revisions_set_updated_at
    BEFORE UPDATE ON dc_block_revisions
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_project_stage_drafts_set_updated_at
    BEFORE UPDATE ON project_stage_drafts
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_project_stage_state_set_updated_at
    BEFORE UPDATE ON project_stage_state
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

COMMIT;
