import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Analysis } from './models';

interface Bar {
  x: number;
  y: number;
  w: number;
  h: number;
  center: number;
  count: number;
}

/**
 * 蒙特卡洛经验分布直方图，并叠加：
 * - 红色区间：最坏极值 [WC_min, WC_max]（保证包络）
 * - 绿色区间：RSS 均值 ± kσ（统计区间，前提不同）
 * 两种区间不能互相替代，故并列展示并标注前提。
 */
@Component({
  selector: 'app-comparison-chart',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
  @if (data(); as a) {
    @if (a.monte_carlo) {
      <svg [attr.viewBox]="'0 0 ' + W + ' ' + H" class="chart" role="img"
           aria-label="最坏极值、均方根与蒙特卡洛分布对比图">
        <!-- 直方图 -->
        @for (b of bars(); track $index) {
          <rect [attr.x]="b.x" [attr.y]="b.y" [attr.width]="b.w" [attr.height]="b.h"
                class="bar" rx="1">
            <title>区间中点 {{ fmt(b.center) }} mm；样本 {{ b.count }}</title>
          </rect>
        }

        <!-- 零线 -->
        @if (zeroX() !== null) {
          <line [attr.x1]="zeroX()!" [attr.y1]="padTop"
                [attr.x2]="zeroX()!" [attr.y2]="H - padBottom"
                class="zero-line"></line>
          <text [attr.x]="zeroX()! + 3" [attr.y]="padTop + 10" class="axis-tag">0（间隙/过盈分界）</text>
        }

        <!-- RSS ±kσ 区间 -->
        @if (a.rss) {
          <line [attr.x1]="xOf(a.rss.lower_mm)" [attr.y1]="bandY + 18"
                [attr.x2]="xOf(a.rss.upper_mm)" [attr.y2]="bandY + 18"
                class="rss-line"></line>
          <text [attr.x]="xOf(a.rss.mean_mm)" [attr.y]="bandY + 34" text-anchor="middle"
                class="rss-tag">RSS 均值±{{ a.rss.k_sigma }}σ =
            [{{ fmt(a.rss.lower_mm) }}, {{ fmt(a.rss.upper_mm) }}]</text>
        }

        <!-- WC 极值区间 -->
        <line [attr.x1]="xOf(a.worst_case.minimum_mm)" [attr.y1]="bandY"
              [attr.x2]="xOf(a.worst_case.maximum_mm)" [attr.y2]="bandY"
              class="wc-line"></line>
        <text [attr.x]="xOf(a.worst_case.minimum_mm)" [attr.y]="bandY - 6" text-anchor="middle"
              class="wc-tag">{{ fmt(a.worst_case.minimum_mm) }}</text>
        <text [attr.x]="xOf(a.worst_case.maximum_mm)" [attr.y]="bandY - 6" text-anchor="middle"
              class="wc-tag">{{ fmt(a.worst_case.maximum_mm) }}</text>
        <text [attr.x]="padLeft" [attr.y]="bandY + 4" class="band-name">WC 保证包络</text>

        <!-- 横轴刻度 -->
        @for (t of ticks(); track t) {
          <line [attr.x1]="xOf(t)" [attr.y1]="H - padBottom"
                [attr.x2]="xOf(t)" [attr.y2]="H - padBottom + 4" class="tick"></line>
          <text [attr.x]="xOf(t)" [attr.y]="H - padBottom + 16" text-anchor="middle"
                class="axis-tag">{{ fmt(t) }}</text>
        }
      </svg>
    } @else {
      <div class="blocked">
        统计分布图不可用：分布前提不满足（见“前提与阻断”）。最坏极值区间仍为
        [{{ fmt(a.worst_case.minimum_mm) }}, {{ fmt(a.worst_case.maximum_mm) }}] mm。
      </div>
    }
  }
  `,
  styles: [`
    .chart { width: 100%; height: auto; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; }
    .bar { fill: #93c5fd; }
    .bar:hover { fill: #2563eb; }
    .zero-line { stroke: #64748b; stroke-width: 1; stroke-dasharray: 4 3; }
    .wc-line { stroke: #b91c1c; stroke-width: 4; }
    .wc-tag { font-size: 10px; fill: #b91c1c; font-weight: 700; }
    .band-name { font-size: 10px; fill: #b91c1c; font-weight: 600; }
    .rss-line { stroke: #15803d; stroke-width: 3; }
    .rss-tag { font-size: 10px; fill: #15803d; font-weight: 600; }
    .tick { stroke: #94a3b8; stroke-width: 1; }
    .axis-tag { font-size: 10px; fill: #475569; }
    .blocked { padding: 16px; background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px;
               color: #92400e; font-size: 13px; }
  `],
})
export class ComparisonChartComponent {
  readonly data = input.required<Analysis>();

  readonly W = 920;
  readonly H = 300;
  readonly padLeft = 60;
  readonly padRight = 30;
  readonly padTop = 18;
  readonly padBottom = 40;
  readonly bandY = 42;

  private readonly domain = computed(() => {
    const a = this.data();
    if (!a) return { lo: 0, hi: 1 };
    let lo = a.worst_case.minimum_mm;
    let hi = a.worst_case.maximum_mm;
    if (a.rss) {
      lo = Math.min(lo, a.rss.lower_mm);
      hi = Math.max(hi, a.rss.upper_mm);
    }
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.08 || 0.01;
    return { lo: lo - pad, hi: hi + pad };
  });

  xOf(v: number): number {
    const { lo, hi } = this.domain();
    return this.padLeft + ((v - lo) / (hi - lo)) * (this.W - this.padLeft - this.padRight);
  }

  readonly zeroX = computed(() => {
    const { lo, hi } = this.domain();
    return lo <= 0 && hi >= 0 ? this.xOf(0) : null;
  });

  readonly bars = computed<Bar[]>(() => {
    const a = this.data();
    if (!a?.monte_carlo) return [];
    const { bin_edges, counts } = a.monte_carlo.histogram;
    const maxCount = Math.max(...counts, 1);
    const top = this.padTop + 40;
    const bottom = this.H - this.padBottom;
    const plotH = bottom - top;
    return bin_edges.slice(0, -1).map((left, i) => {
      const right = bin_edges[i + 1];
      const h = (counts[i] / maxCount) * plotH;
      return {
        x: this.xOf(left),
        y: bottom - h,
        w: Math.max(this.xOf(right) - this.xOf(left) - 0.5, 0.5),
        h,
        center: (left + right) / 2,
        count: counts[i],
      };
    });
  });

  readonly ticks = computed(() => {
    const { lo, hi } = this.domain();
    const n = 6;
    const step = (hi - lo) / n;
    return Array.from({ length: n + 1 }, (_, i) => lo + step * i);
  });

  fmt(v: number): string {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const abs = Math.abs(v);
    const digits = abs >= 10 ? 3 : abs >= 1 ? 4 : 5;
    return v.toFixed(digits);
  }
}
