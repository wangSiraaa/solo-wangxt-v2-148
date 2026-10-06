import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Chain, WorstCase } from './models';

interface Node {
  x: number;
  y: number;
}

interface Edge {
  name: string;
  detail: string;
  sign: 1 | -1;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  labelX: number;
  labelY: number;
  color: string;
}

/**
 * 闭合尺寸链示意图（SVG）：
 * 从基准节点出发，沿组成环依次推进（增环 + / 减环 − 分色），
 * 末端用虚线“封闭环”弧回到起点，构成闭环。
 * 纯示意布局（等距），不按名义尺寸比例绘制，避免误导。
 */
@Component({
  selector: 'app-chain-diagram',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
  <svg [attr.viewBox]="'0 0 ' + width + ' ' + height" class="chain-svg" role="img"
       [attr.aria-label]="'闭合尺寸链：' + chain().closing_name">
    <defs>
      <marker id="arrow-inc" markerWidth="9" markerHeight="9" refX="8" refY="3.5" orient="auto">
        <path d="M0,0 L8,3.5 L0,7 z" fill="#15803d"></path>
      </marker>
      <marker id="arrow-dec" markerWidth="9" markerHeight="9" refX="8" refY="3.5" orient="auto">
        <path d="M0,0 L8,3.5 L0,7 z" fill="#c2410c"></path>
      </marker>
      <marker id="arrow-close" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto">
        <path d="M0,0 L9,4 L0,8 z" fill="#b91c1c"></path>
      </marker>
    </defs>

    <!-- 组成环边 -->
    @for (e of edges(); track e.name) {
      <line [attr.x1]="e.x1" [attr.y1]="e.y1" [attr.x2]="e.x2" [attr.y2]="e.y2"
            [attr.stroke]="e.color" stroke-width="2.5"
            [attr.marker-end]="e.sign === 1 ? 'url(#arrow-inc)' : 'url(#arrow-dec)'">
        <title>{{ e.name }}：{{ e.detail }}</title>
      </line>
      <text [attr.x]="e.labelX" [attr.y]="e.labelY - 8" text-anchor="middle"
            class="edge-label" [attr.fill]="e.color">{{ e.sign === 1 ? '+' : '−' }}{{ e.name }}</text>
      <text [attr.x]="e.labelX" [attr.y]="e.labelY + 10" text-anchor="middle" class="edge-detail">{{ e.detail }}</text>
    }

    <!-- 节点 -->
    @for (n of nodesWithStart(); track $index) {
      <circle [attr.cx]="n.x" [attr.cy]="n.y" r="5"
              [attr.fill]="$first || $last ? '#334155' : '#e2e8f0'"
              [attr.stroke]="'#334155'" stroke-width="1.5"></circle>
      @if ($first) {
        <text [attr.x]="n.x" [attr.y]="n.y - 16" text-anchor="middle" class="node-label">基准</text>
      }
    }

    <!-- 封闭环回程弧 -->
    <path [attr.d]="closePath()" fill="none" stroke="#b91c1c" stroke-width="2.5"
          stroke-dasharray="7 5" marker-end="url(#arrow-close)"></path>
    <text [attr.x]="width / 2" [attr.y]="height - 34" text-anchor="middle" class="close-label">
      封闭环：{{ chain().closing_name }}
    </text>
    <text [attr.x]="width / 2" [attr.y]="height - 16" text-anchor="middle" class="close-detail">
      {{ chain().closing_positive_direction }}
      @if (wc(); as w) {
        · 极值区间 [{{ fmt(w.minimum_mm) }}, {{ fmt(w.maximum_mm) }}] mm
      }
    </text>
  </svg>
  `,
  styles: [`
    .chain-svg { width: 100%; height: auto; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
    .edge-label { font-size: 13px; font-weight: 600; }
    .edge-detail { font-size: 11px; fill: #475569; }
    .node-label { font-size: 11px; fill: #334155; font-weight: 600; }
    .close-label { font-size: 13px; font-weight: 700; fill: #b91c1c; }
    .close-detail { font-size: 11px; fill: #7f1d1d; }
  `],
})
export class ChainDiagramComponent {
  readonly chain = input.required<Chain>();
  readonly wc = input<WorstCase | null>(null);

  readonly width = 920;
  readonly height = 230;
  private readonly y = 78;

  readonly nodes = computed<Node[]>(() => {
    const chain = this.chain();
    if (!chain) return [];
    const n = chain.dimensions.length;
    const marginX = 70;
    const usable = this.width - marginX * 2;
    const step = n > 1 ? usable / n : usable;
    const out: Node[] = [{ x: marginX, y: this.y }];
    chain.dimensions.forEach((_, i) => out.push({ x: marginX + step * (i + 1), y: this.y }));
    return out;
  });

  readonly nodesWithStart = computed<Node[]>(() => this.nodes());

  readonly edges = computed<Edge[]>(() => {
    const chain = this.chain();
    const nodes = this.nodes();
    if (!chain || nodes.length < 2) return [];
    return chain.dimensions.map((d, i) => {
      const a = nodes[i];
      const b = nodes[i + 1];
      const reverse = d.direction === -1;
      return {
        name: d.name,
        detail: `${this.fmt(d.nominal)} ${d.dimension_unit} (${this.fmt(d.lower_deviation)}/${this.fmt(d.upper_deviation)})`,
        sign: d.direction,
        x1: reverse ? b.x : a.x,
        y1: this.y,
        x2: reverse ? a.x : b.x,
        y2: this.y,
        labelX: (a.x + b.x) / 2,
        labelY: this.y,
        color: d.direction === 1 ? '#15803d' : '#c2410c',
      };
    });
  });

  readonly closePath = computed(() => {
    const nodes = this.nodes();
    if (nodes.length < 2) return '';
    const start = nodes[nodes.length - 1];
    const end = nodes[0];
    const midY = this.height - 70;
    // 从末端下探、走下半圆弧回到基准
    return `M ${start.x} ${start.y + 6}
            C ${start.x} ${midY + 20}, ${end.x} ${midY + 20}, ${end.x} ${end.y + 6}`;
  });

  fmt(v: number): string {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const abs = Math.abs(v);
    const digits = abs >= 10 ? 3 : abs >= 1 ? 4 : 5;
    return v.toFixed(digits);
  }
}
