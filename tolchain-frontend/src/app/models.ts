/** 后端 API 的类型镜像（只保留 UI 用到的字段）。 */

export type Direction = 1 | -1;
export type DistributionKind = 'normal' | 'uniform' | 'triangular' | 'deterministic' | 'unknown';
export type DimensionSource = 'design' | 'measured' | 'thermal_expansion' | 'datum' | 'other';

export interface Dimension {
  id?: number;
  chain_id?: number;
  position?: number;
  name: string;
  nominal: number;
  lower_deviation: number;
  upper_deviation: number;
  dimension_unit: string;
  direction: Direction;
  source: DimensionSource;
  source_detail?: string | null;
  distribution_kind: DistributionKind;
  distribution_params: Record<string, unknown>;
}

export interface Chain {
  id: number;
  name: string;
  description?: string | null;
  base_unit: string;
  closing_name: string;
  closing_positive_direction: string;
  expected_closing_nominal?: number | null;
  acceptance_lower?: number | null;
  acceptance_upper?: number | null;
  dimensions: Dimension[];
}

export interface Contributor {
  key: string;
  name: string;
  direction: 1 | -1;
  band_width_mm?: number;
  share: number;
  variance_mm2?: number;
  std_mm?: number;
  spearman_with_closing?: number;
}

export interface WorstCase {
  nominal_mm: number;
  upper_deviation_mm: number;
  lower_deviation_mm: number;
  maximum_mm: number;
  minimum_mm: number;
  tolerance_span_mm: number;
  sum_absolute_tolerances_mm: number;
  absolute_sum_note: string;
  contributors: Contributor[];
  premises: string;
}

export interface Rss {
  mean_mm: number;
  std_mm: number;
  k_sigma: number;
  lower_mm: number;
  upper_mm: number;
  mean_shift_from_nominal_mm: number;
  contributors: Contributor[];
  premises: string;
}

export interface MonteCarlo {
  n_samples: number;
  seed: number;
  mean_mm: number;
  std_mm: number;
  p0_1_mm: number;
  p1_mm: number;
  p5_mm: number;
  p50_mm: number;
  p95_mm: number;
  p99_mm: number;
  p99_9_mm: number;
  sample_min_mm: number;
  sample_max_mm: number;
  histogram: { bin_edges: number[]; counts: number[] };
  analytical_extreme_check: {
    wc_min_mm: number;
    wc_max_mm: number;
    samples_below_wc_min: number;
    samples_above_wc_max: number;
    within_physical_envelope: boolean;
    note: string;
  };
  acceptance_estimate?: {
    lower_mm: number | null;
    upper_mm: number | null;
    fraction_within: number;
    fraction_outside: number;
    note: string;
  };
  contributors: Contributor[];
  premises: string;
}

export interface Analysis {
  base_unit: string;
  worst_case: WorstCase;
  rss: Rss | null;
  monte_carlo: MonteCarlo | null;
  statistical_blockers: string[];
  assumption_notes: string[];
  warnings: string[];
  unit_conversions: { name: string; from_unit: string; factor_to_base: number }[];
  nominal_residual_mm: number | null;
  cross_check: { mean_abs_diff_mm: number; std_relative_diff: number; note: string } | null;
  dominance_summary: {
    tolerance_band_dominator: Contributor | null;
    variance_dominator: Contributor | null;
    sampling_dominator: Contributor | null;
  };
  disclaimer: string;
  chain: {
    id: number;
    name: string;
    closing_name: string;
    closing_positive_direction: string;
    base_unit: string;
  };
}
