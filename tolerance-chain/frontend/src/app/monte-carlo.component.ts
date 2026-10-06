import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { McResult } from './models';
import { fmt, pct } from './format';

@Component({
  selector: 'app-monte-carlo',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="method-card">
      <h3>③ 蒙特卡洛（固定种子抽样）</h3>
      <div class="premise">{{ data.premise }}</div>

      <div class="metric"><span>样本数 / 种子</span>
        <span class="v">{{ data.n_samples.toLocaleString() }} / {{ data.seed }}</span></div>
      <div class="metric"><span>样本均值</span>
        <span class="v">{{ fmt(data.sample_mean) }}</span></div>
      <div class="metric"><span>样本标准差</span>
        <span class="v">{{ fmt(data.sample_sd, 5) }}</span></div>
      <div class="metric"><span>p05 / p50 / p95</span>
        <span class="v">{{ fmt(data.p05) }} / {{ fmt(data.p50) }} / {{ fmt(data.p95) }}</span></div>
      <div class="metric"><span>样本极值 min / max</span>
        <span class="v">{{ fmt(data.sample_min) }} / {{ fmt(data.sample_max) }}</span></div>
      <div class="metric"><span>超出解析极值的样本</span>
        <span class="v">
          <span class="tag" [class.ok]="data.samples_outside_extremes === 0"
                [class.warn]="data.samples_outside_extremes > 0">
            {{ data.samples_outside_extremes }} ({{ pct(data.outside_fraction) }})
          </span>
        </span></div>
      <div class="metric"><span>干涉比例（gap ≤ 0）</span>
        <span class="v" [class.dir-neg]="data.interference_fraction > 0">
          {{ pct(data.interference_fraction) }}</span></div>

      <div class="premise" [style.border-left-color]="
          data.samples_outside_extremes === 0 ? '#2b6cb0' : '#d98324'">
        {{ data.outside_note }}
      </div>

      <div *ngFor="let r of data.per_ring" class="bar-row">
        <span [class.dominant]="r.key === data.dominant_key">
          {{ r.name }}
          <span class="tag" *ngIf="r.sample_sd === 0">零公差常数</span>
          <span class="tag" *ngIf="r.sample_sd !== 0">{{ r.distribution }}</span>
        </span>
        <span class="bar-track">
          <span class="bar-fill"
                [class.zero]="r.sample_sd === 0"
                [style.width.%]="Math.abs(r.variance_share) * 100"></span>
        </span>
        <span class="bar-val">{{ pct(r.variance_share) }}</span>
      </div>
      <div class="source" style="margin-top:6px">
        样本方差主导尺寸：<strong>{{ data.dominant_name }}</strong>
        （协方差份额 Cov(xᵢ,gap)/Var(gap)，同种子可复现）
      </div>
    </div>
  `,
})
export class MonteCarloComponent {
  @Input({ required: true }) data!: McResult;
  fmt = fmt; pct = pct;
  Math = Math;
}
