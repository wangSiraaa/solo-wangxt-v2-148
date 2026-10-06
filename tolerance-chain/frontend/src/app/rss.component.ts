import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RssResult } from './models';
import { fmt, pct } from './format';

@Component({
  selector: 'app-rss',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="method-card">
      <h3>② 均方根（RSS / 统计公差）</h3>
      <div class="premise">{{ data.premise }}</div>

      <div class="metric"><span>封闭环均值 μ</span>
        <span class="v">{{ fmt(data.gap_mean) }}</span></div>
      <div class="metric"><span>封闭环标准差 σ</span>
        <span class="v">{{ fmt(data.gap_sd, 5) }}</span></div>
      <div class="metric"><span>±{{ data.k_sigma }}σ 区间</span>
        <span class="v">[{{ fmt(data.gap_low_k_sigma) }},
          {{ fmt(data.gap_high_k_sigma) }}]</span></div>
      <div class="metric"><span>解析极值界限</span>
        <span class="v">[{{ fmt(data.worst_gap_min) }},
          {{ fmt(data.worst_gap_max) }}]</span></div>

      <div class="premise" style="border-left-color:#2b6cb0">
        {{ data.bounded_note }}
      </div>

      <div *ngFor="let r of data.per_ring" class="bar-row">
        <span [class.dominant]="r.key === data.dominant_key">
          {{ r.name }}
          <span class="tag">{{ r.distribution }}</span>
        </span>
        <span class="bar-track">
          <span class="bar-fill"
                [style.width.%]="r.variance_share * 100"></span>
        </span>
        <span class="bar-val">{{ pct(r.variance_share) }}</span>
      </div>
      <div class="source" style="margin-top:6px">
        方差主导尺寸：<strong>{{ data.dominant_name }}</strong>
        （σ_i²/Σσ²；单边公差的均值移动已计入 μ）
      </div>
    </div>
  `,
})
export class RssComponent {
  @Input({ required: true }) data!: RssResult;
  fmt = fmt; pct = pct;
}
