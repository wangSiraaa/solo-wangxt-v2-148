import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WorstCaseResult } from './models';
import { fmt, pct } from './format';

@Component({
  selector: 'app-worst-case',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="method-card">
      <h3>① 最坏情况（极值法 WC）</h3>
      <div class="premise">{{ data.premise }}</div>

      <div class="metric"><span>封闭环公称值</span>
        <span class="v">{{ fmt(data.nominal) }}</span></div>
      <div class="metric"><span>最小间隙 gap_min</span>
        <span class="v" [class.dir-neg]="data.gap_min < 0">{{ fmt(data.gap_min) }}</span></div>
      <div class="metric"><span>最大间隙 gap_max</span>
        <span class="v">{{ fmt(data.gap_max) }}</span></div>
      <div class="metric"><span>封闭环中心</span>
        <span class="v">{{ fmt(data.gap_center) }}</span></div>
      <div class="metric"><span>可能干涉（min &lt; 0）</span>
        <span class="tag" [class.bad]="data.interference_possible"
              [class.ok]="!data.interference_possible">
          {{ data.interference_possible ? '是' : '否' }}</span></div>

      <div class="warn-box" *ngIf="data.naive_warning">
        ⚠️ 朴素做法“所有公差绝对值直接相加” = {{ fmt(data.naive_absolute_sum) }}，
        在本链中 <strong>不能当作最终间隙</strong>：{{ data.naive_warning }}
      </div>
      <div class="warn-box" *ngIf="!data.naive_warning" style="background:#eef6ef;border-color:#c3e0ca;color:#2b6a3a">
        本链全部为关于公称对称的双向公差，绝对值带宽 = {{ fmt(data.naive_absolute_sum) }}
        恰好等于极值带宽，但仍不包含封闭环中心信息。
      </div>

      <table>
        <thead><tr>
          <th>组成环</th><th class="num">方向</th>
          <th class="num">最小贡献</th><th class="num">最大贡献</th>
          <th class="num">公差半宽</th><th class="num">极值主导份额</th>
        </tr></thead>
        <tbody>
          <tr *ngFor="let r of data.per_ring"
              [class.dominant]="r.key === data.dominant_key">
            <td>{{ r.name }}
              <span class="tag" *ngIf="r.half_width === 0">零公差</span></td>
            <td class="num" [class.dir-pos]="r.direction === 1"
                [class.dir-neg]="r.direction === -1">
              {{ r.direction === 1 ? '+1 增环' : '−1 减环' }}</td>
            <td class="num">{{ fmt(r.min_contribution) }}</td>
            <td class="num">{{ fmt(r.max_contribution) }}</td>
            <td class="num">{{ fmt(r.half_width) }}</td>
            <td class="num">{{ pct(r.dominance_share) }}</td>
          </tr>
        </tbody>
      </table>
      <div class="source" style="margin-top:6px">
        极值主导尺寸：<strong>{{ data.dominant_name }}</strong>（按公差半宽占比）
      </div>
    </div>
  `,
})
export class WorstCaseComponent {
  @Input({ required: true }) data!: WorstCaseResult;
  fmt = fmt; pct = pct;
}
