// Data types for HiLabs Provider Rates Dashboard

export interface C4Summary {
  stage: string;
  status: string;
  input_file: string;
  source_rate_file_url: string;
  negotiated_rates_processed: number;
  negotiated_rate_entries_processed: number;
  service_entries_processed: number;
  services_processed: number;
  curated_records: number;
  distinct_npis: number;
  distinct_npis_curated: number;
  distinct_tins: number;
  distinct_tins_curated: number;
  distinct_provider_group_ids_referenced: number;
  distinct_unresolved_provider_group_ids: number;
  output_records_generated: number;
  exact_duplicates: number;
  exact_duplicates_removed: number;
  alternative_candidates_removed: number;
  records_rejected: number;
  rejection_reasons: Record<string, number>;
  invalid_rates: number;
  missing_invalid_nonnumeric_rates: number;
  negative_rates: number;
  zero_rates: number;
  negative_rate_records: number;
  zero_rate_records: number;
  c3_quality_score: number;
  unresolved_provider_references: number;
  unresolved_provider_references_count: number;
  outputs: Record<string, string>;
  git_sha?: string;
  runtime_seconds?: number;
}

export interface C5Summary {
  stage: string;
  input_c4_rows: number;
  output_rows: number;
  distinct_valid_npis: number;
  distinct_tins: number;
  address_matched_rows: number;
  corroborated: number;
  single_source: number;
  conflicting: number;
  unresolved: number;
  duplicate_four_key_rows: number;
  invalid_npi_count: number;
  specialty_mapped: number;
  specialty_unmapped: number;
  nucc_mapped_codes: number;
  api_status: string;
  cms_file: string;
  nppes_zip: string;
  nucc_file: string;
  sources: string[];
  unverified_tin_address_links: number;
  git_sha?: string;
  runtime_seconds?: number;
}

export interface ManifestCounts {
  files_scored?: number;
  price_rows_scored?: number;
  plan_file_rows?: number;
  unique_rate_files?: number;
  candidate_rate_files?: number;
  plans_classified?: number;
  ppo_plans?: number;
  curated_records?: number;
  distinct_npis?: number;
  distinct_tins?: number;
  exact_duplicate_records?: number;
  missing_invalid_nonnumeric_rates?: number;
  negative_rates?: number;
  negotiated_rate_entries_processed?: number;
  output_records_generated?: number;
  records_rejected?: number;
  service_entries_processed?: number;
  unresolved_provider_references?: number;
  zero_rates?: number;
  address_matched_rows?: number;
  distinct_valid_npis?: number;
  input_c4_rows?: number;
  invalid_npi_count?: number;
  output_rows?: number;
  unresolved?: number;
  c5_rows?: number;
  c6_rows?: number;
  duplicate_keys?: number;
  groups?: number;
  ambiguous?: number;
  fuzzy_county_matches?: number;
  locality_fallback?: number;
  pfs_matched?: number;
  providers?: number;
  rows?: number;
}

export interface C7Summary {
  stage: string;
  rows: number;
  providers: number;
  pfs_matched: number;
  locality_fallback: number;
  fuzzy_county_matches: number;
  median_medicare_ratio: number;
  mean_medicare_ratio: number;
  tier_a: number;
  tier_b: number;
  tier_c: number;
  deliverables: string[];
  manifest?: Manifest;
}

export interface Manifest {
  stage: string;
  config_sha256: string;
  counts: ManifestCounts;
  git_sha: string;
  runtime_seconds: number;
  sources: Array<{
    path: string;
    size?: number;
    last_modified?: number;
    sha256?: string;
    member?: string;
    archive_member?: string;
    rows?: number;
  }>;
}

export interface KPIData {
  ratesExtracted: number;
  npis: number;
  tins: number;
  verifiedAddressesPct: number;
  fileGrade: string;
}

export interface PipelineStage {
  stage: string;
  label: string;
  status: "completed" | "running" | "pending" | "failed";
  runtime_seconds?: number;
  records_in?: number;
  records_out?: number;
}

export interface UnresolvedRecord {
  npi: string;
  tin: string;
  specialty: string;
  reason: string;
  evidence_tier: string;
}

export interface SourceTierBreakdown {
  label: string;
  value: number;
  color: string;
}

export interface RateFilterOptions {
  billingCodes: string[];
  specialties: string[];
  addressStatuses: Array<{ value: string; label: string }>;
}

export interface AddressStatusData {
  corroborated: number;
  single_source: number;
  conflicting: number;
  unresolved: number;
  total: number;
  unresolvedRecords?: UnresolvedRecord[];
  tiers?: SourceTierBreakdown[];
}

export interface FileQualityData {
  grade: string;
  score: number;
  metrics: Array<{
    name: string;
    value: number | string;
    status: "pass" | "warn" | "fail";
  }>;
  outliers: Array<{
    type: string;
    count: number;
    severity: "high" | "medium" | "low";
  }>;
}

export interface RateRecord {
  npi: string;
  tin: string;
  address: string;
  billing_code: string;
  specialty: string;
  rate: number;
  address_status: string;
  specialty_source: string;
  selection_rule?: string;
  candidate_count?: number;
  alternatives?: RateRecord[];
}

export interface AuditEntry {
  stage: string;
  timestamp: string;
  git_sha: string;
  runtime_seconds: number;
  counts: ManifestCounts;
}