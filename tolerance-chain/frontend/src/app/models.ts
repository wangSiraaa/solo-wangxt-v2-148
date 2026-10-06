/** 与后端 schemas 对应的类型定义。 */

export type Direction = 1 | -1;
export type Distribution =
  | 'unknown' | 'normal' | 'uniform' | 'triangular' | 'halfnormal';

export interface Ring {
  id?: number;
  key: string;
  name: string;
  source: string;
  direction: Direction;
  nominal: number;
  es: number;
  ei: number;
  unit: string;
  distribution: Distribution;
  dist_params: Record<string, number>;
  note?: string;
  position?: number;
  // 后端换算/计算后附加
  one_sided?: boolean;
  zero_tolerance?: boolean;
}

export interface Chain {
  id: number;
  code: string;
  name: string;
  description: string;
  closed_unit: string;
  closed_name: string;
  rings: Ring[];
}

export interface PerRingWc {
  key: string; name: string; direction: number;
  min_contribution: number; max_contribution: number;
  half_width: number; dominance_share: number;
}
export interface PerRingStat {
  key: string; name: string; direction: number; distribution: string;
  dev_mean?: number; dev_sd?: number;
  sample_mean?: number; sample_sd?: number;
  variance_share: number;
}

export interface WorstCaseResult {
  method: 'worst_case';
  premise: string;
  nominal: number;
  gap_min: number; gap_max: number; gap_center: number; total_span: number;
  naive_absolute_sum: number;
  naive_absolute_sum_correct: boolean;
  naive_warning: string | null;
  interference_possible: boolean;
  per_ring: PerRingWc[];
  dominant_key: string; dominant_name: string;
}

export interface RssResult {
  method: 'rss';
  premise: string;
  k_sigma: number;
  nominal: number;
  gap_mean: number; gap_sd: number;
  gap_low_k_sigma: number; gap_high_k_sigma: number;
  bounded_within_extremes: boolean;
  bounded_note: string;
  worst_gap_min: number; worst_gap_max: number;
  per_ring: PerRingStat[];
  dominant_key: string; dominant_name: string;
}

export interface McResult {
  method: 'monte_carlo';
  premise: string;
  seed: number; n_samples: number;
  nominal: number;
  sample_mean: number; sample_sd: number;
  p05: number; p50: number; p95: number;
  sample_min: number; sample_max: number;
  worst_gap_min: number; worst_gap_max: number;
  samples_outside_extremes: number;
  outside_fraction: number; outside_note: string;
  interference_fraction: number;
  per_ring: PerRingStat[];
  dominant_key: string; dominant_name: string;
}

export interface AnalysisResult {
  closed_unit: string;
  rings_used: Ring[];
  results: {
    worst_case?: WorstCaseResult;
    rss?: RssResult;
    monte_carlo?: McResult;
  };
  method_errors: Record<string, string>;
  disclaimer: string;
}

export interface Run {
  id: number; chain_id: number;
  seed: number; n_samples: number; k_sigma: number;
  result: AnalysisResult;
}
