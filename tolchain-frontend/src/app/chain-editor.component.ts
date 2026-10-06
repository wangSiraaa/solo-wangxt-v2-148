import { ChangeDetectionStrategy, Component, EventEmitter, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from './api.service';
import { Dimension } from './models';

function emptyDim(): Dimension {
  return {
    name: '',
    nominal: 0,
    lower_deviation: 0,
    upper_deviation: 0,
    dimension_unit: 'mm',
    direction: 1,
    source: 'design',
    source_detail: '',
    distribution_kind: 'unknown',
    distribution_params: {},
  };
}

@Component({
  selector: 'app-chain-editor',
  standalone: true,
  imports: [FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
  <div class="editor">
    <h3>新建尺寸链</h3>
    <div class="grid2">
      <label>名称<input [(ngModel)]="name" placeholder="如：轴孔配合 φ20 H7/g6"></label>
      <label>封闭环名称<input [(ngModel)]="closingName" placeholder="如：装配间隙 G"></label>
    </div>
    <label class="full">封闭环正方向定义
      <input [(ngModel)]="closingDir"
             placeholder="如：G = 孔径 − 轴径；G&gt;0 为间隙，G&lt;0 为过盈">
    </label>
    <div class="grid3">
      <label>目标名义值（用于方向核对，可选）
        <input type="number" step="0.001" [(ngModel)]="expectedNominal"></label>
      <label>验收下界 mm（可选）<input type="number" step="0.001" [(ngModel)]="acceptLower"></label>
      <label>验收上界 mm（可选）<input type="number" step="0.001" [(ngModel)]="acceptUpper"></label>
    </div>

    <h4>组成环（{{ dims().length }}）</h4>
    @for (d of dims(); track $index) {
      <div class="dim-row">
        <button class="del" type="button" title="删除该环" (click)="remove($index)">×</button>
        <input [(ngModel)]="d.name" placeholder="名称">
        <input type="number" [(ngModel)]="d.nominal" placeholder="名义值">
        <input type="number" [(ngModel)]="d.lower_deviation" placeholder="下偏差">
        <input type="number" [(ngModel)]="d.upper_deviation" placeholder="上偏差">
        <select [(ngModel)]="d.dimension_unit">
          <option value="mm">mm</option>
          <option value="um">µm</option>
          <option value="inch">inch</option>
        </select>
        <select [(ngModel)]="d.direction" [class.dec]="d.direction === -1">
          <option [ngValue]="1">+ 增环</option>
          <option [ngValue]="-1">− 减环</option>
        </select>
        <select [(ngModel)]="d.source">
          <option value="design">图纸设计</option>
          <option value="measured">实测统计</option>
          <option value="thermal_expansion">热膨胀线性项</option>
          <option value="datum">零公差基准</option>
          <option value="other">其它</option>
        </select>
        <select [(ngModel)]="d.distribution_kind">
          <option value="unknown">未知（不做统计）</option>
          <option value="normal">正态（截断，带中点为均值）</option>
          <option value="uniform">均匀</option>
          <option value="triangular">三角</option>
          <option value="deterministic">确定性/零公差</option>
        </select>
      </div>
    }
    <div class="row-actions">
      <button type="button" class="secondary" (click)="add()">＋ 添加组成环</button>
      <button type="button" class="secondary" (click)="thermalOpen.set(!thermalOpen())">
        {{ thermalOpen() ? '收起' : '热膨胀项助手 ΔL=α·L·ΔT' }}
      </button>
    </div>

    @if (thermalOpen()) {
      <div class="thermal">
        <div class="grid4">
          <label>α (1/°C)<input type="number" [(ngModel)]="th.alpha" placeholder="1.2e-5"></label>
          <label>L (mm)<input type="number" [(ngModel)]="th.length"></label>
          <label>ΔT 名义 (°C)<input type="number" [(ngModel)]="th.dt"></label>
          <label>ΔT 不确定下界<input type="number" [(ngModel)]="th.dtLo" placeholder="单边填 0"></label>
          <label>ΔT 不确定上界<input type="number" [(ngModel)]="th.dtHi"></label>
          <label>不确定分布
            <select [(ngModel)]="th.kind">
              <option value="uniform">均匀</option>
              <option value="triangular">三角</option>
              <option value="unknown">未知</option>
            </select>
          </label>
        </div>
        <button type="button" class="secondary" (click)="addThermal()">生成并追加为组成环（方向 +1，冷缩用负 ΔT）</button>
      </div>
    }

    @if (error()) { <p class="error">{{ error() }}</p> }
    <button type="button" class="primary" (click)="submit()">保存尺寸链</button>
  </div>
  `,
  styles: [`
    .editor { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
    .grid4 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 8px; }
    label { display: flex; flex-direction: column; font-size: 12px; color: #475569; gap: 3px; margin: 8px 0; }
    .full { width: 100%; }
    input, select { padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; }
    h3 { margin: 0 0 10px; } h4 { margin: 14px 0 6px; color: #334155; }
    .dim-row { display: grid; grid-template-columns: 28px 1.2fr .8fr .8fr .8fr .7fr .8fr .9fr 1.1fr;
               gap: 6px; align-items: center; margin-bottom: 6px; }
    .dim-row select.dec { border-color: #c2410c; color: #c2410c; }
    .del { background: #fee2e2; color: #b91c1c; border: none; border-radius: 50%; width: 24px; height: 24px;
           cursor: pointer; font-weight: 700; }
    .row-actions { display: flex; gap: 8px; margin: 8px 0; }
    .thermal { background: #f1f5f9; border-radius: 8px; padding: 10px; margin: 8px 0; }
    .primary { background: #1d4ed8; color: #fff; border: none; border-radius: 6px; padding: 9px 18px;
               cursor: pointer; font-weight: 600; margin-top: 10px; }
    .secondary { background: #e2e8f0; border: none; border-radius: 6px; padding: 7px 12px; cursor: pointer; }
    .error { color: #b91c1c; font-size: 13px; }
  `],
})
export class ChainEditorComponent {
  private readonly api = inject(ApiService);

  @Output() saved = new EventEmitter<void>();

  name = '';
  closingName = '';
  closingDir = '';
  expectedNominal: number | null = null;
  acceptLower: number | null = null;
  acceptUpper: number | null = null;

  readonly dims = signal<Dimension[]>([emptyDim()]);
  readonly thermalOpen = signal(false);
  readonly error = signal('');

  th = { alpha: 1.2e-5, length: 100, dt: 40, dtLo: 0, dtHi: 10, kind: 'uniform' as 'uniform' | 'triangular' | 'unknown' };

  add(): void { this.dims.update((list) => [...list, emptyDim()]); }
  remove(i: number): void { this.dims.update((list) => list.filter((_, j) => j !== i)); }

  addThermal(): void {
    this.api
      .thermalTerm({
        alpha_per_c: Number(this.th.alpha),
        length_mm: Number(this.th.length),
        delta_t_c: Number(this.th.dt),
        delta_t_lower_c: this.th.dtLo === null ? null : Number(this.th.dtLo),
        delta_t_upper_c: this.th.dtHi === null ? null : Number(this.th.dtHi),
        uncertainty_kind: this.th.kind,
      })
      .subscribe({
        next: (term) => {
          const d = emptyDim();
          Object.assign(d, {
            name: term['name'] as string,
            nominal: term['nominal'] as number,
            lower_deviation: term['lower_deviation'] as number,
            upper_deviation: term['upper_deviation'] as number,
            dimension_unit: term['dimension_unit'] as string,
            direction: term['direction'] as 1 | -1,
            source: term['source'] as never,
            source_detail: term['source_detail'] as string,
            distribution_kind: term['distribution_kind'] as never,
            distribution_params: term['distribution_params'] as Record<string, unknown>,
          });
          this.dims.update((list) => [...list, d]);
        },
        error: (e) => this.error.set(e?.error?.detail ?? '热膨胀项生成失败'),
      });
  }

  submit(): void {
    this.error.set('');
    const dims = this.dims().filter((d) => d.name.trim());
    if (!this.name.trim() || !this.closingName.trim() || !this.closingDir.trim()) {
      this.error.set('请填写尺寸链名称、封闭环名称与正方向定义。');
      return;
    }
    if (!dims.length) {
      this.error.set('至少需要一个命名的组成环。');
      return;
    }
    const num = (v: number | null) => (v === null || Number.isNaN(v) ? null : v);
    this.api
      .createChain({
        name: this.name,
        closing_name: this.closingName,
        closing_positive_direction: this.closingDir,
        base_unit: 'mm',
        expected_closing_nominal: num(this.expectedNominal),
        acceptance_lower: num(this.acceptLower),
        acceptance_upper: num(this.acceptUpper),
        dimensions: dims,
      })
      .subscribe({
        next: () => {
          this.name = this.closingName = this.closingDir = '';
          this.expectedNominal = this.acceptLower = this.acceptUpper = null;
          this.dims.set([emptyDim()]);
          this.saved.emit();
        },
        error: (e) => this.error.set(JSON.stringify(e?.error?.detail ?? e)),
      });
  }
}
