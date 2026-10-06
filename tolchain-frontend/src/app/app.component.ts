import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from './api.service';
import { Analysis, Chain, Contributor } from './models';
import { ChainDiagramComponent } from './chain-diagram.component';
import { ComparisonChartComponent } from './comparison-chart.component';
import { ChainEditorComponent } from './chain-editor.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    DecimalPipe,
    FormsModule,
    ChainDiagramComponent,
    ComparisonChartComponent,
    ChainEditorComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly chains = signal<Chain[]>([]);
  readonly selectedId = signal<number | null>(null);
  readonly analysis = signal<Analysis | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly showEditor = signal(false);

  nSamples = 100_000;
  seed: number | null = null;

  readonly selected = computed<Chain | null>(
    () => this.chains().find((c) => c.id === this.selectedId()) ?? null,
  );

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.api.listChains().subscribe({
      next: (chains) => {
        this.chains.set(chains);
        if (this.selectedId() === null && chains.length) {
          this.select(chains[0].id);
        } else if (this.selectedId() !== null) {
          this.runAnalysis();
        }
      },
      error: (e) => this.error.set(`无法连接后端 API：${e?.message ?? e}`),
    });
  }

  select(id: number): void {
    this.selectedId.set(id);
    this.analysis.set(null);
    this.runAnalysis();
  }

  runAnalysis(): void {
    const id = this.selectedId();
    if (id === null) return;
    this.loading.set(true);
    this.error.set('');
    this.api.analyze(id, Number(this.nSamples) || undefined, this.seed ?? undefined).subscribe({
      next: (a) => {
        this.analysis.set(a);
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(e?.error?.detail ?? `分析失败：${e?.message ?? e}`);
        this.loading.set(false);
      },
    });
  }

  seedDemo(): void {
    this.api.seedDemo().subscribe({
      next: () => this.refresh(),
      error: (e) => this.error.set(JSON.stringify(e?.error ?? e)),
    });
  }

  deleteChain(id: number, event: Event): void {
    event.stopPropagation();
    if (!confirm('删除该尺寸链及其组成环与计算记录？')) return;
    this.api.deleteChain(id).subscribe(() => {
      if (this.selectedId() === id) {
        this.selectedId.set(null);
        this.analysis.set(null);
      }
      this.refresh();
    });
  }

  sourceLabel(s: string): string {
    return {
      design: '图纸设计',
      measured: '实测统计',
      thermal_expansion: '热膨胀线性项',
      datum: '零公差基准',
      other: '其它',
    }[s] ?? s;
  }

  distLabel(k: string): string {
    return {
      normal: '截断正态',
      uniform: '均匀',
      triangular: '三角',
      deterministic: '确定性',
      unknown: '未知',
    }[k] ?? k;
  }

  sharePct(c: Contributor): string {
    return `${(c.share * 100).toFixed(1)}%`;
  }

  fmt(v: number | null | undefined, digits = 5): string {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    return v.toFixed(digits);
  }
}
