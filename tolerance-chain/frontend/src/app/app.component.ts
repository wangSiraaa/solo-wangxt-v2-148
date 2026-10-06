import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from './api.service';
import { AnalysisResult, Chain, Run } from './models';
import { WorstCaseComponent } from './worst-case.component';
import { RssComponent } from './rss.component';
import { MonteCarloComponent } from './monte-carlo.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule,
    WorstCaseComponent, RssComponent, MonteCarloComponent],
  template: `
  <div class="container">
    <h1>尺寸公差链分析</h1>
    <p class="subtitle">
      比较装配间隙的 <strong>最坏情况</strong>、<strong>均方根(RSS)</strong> 与
      <strong>蒙特卡洛分布</strong>。方向与单位先校验，再按带符号偏差叠加。
    </p>

    <div class="card">
      <h2 style="margin-top:0">尺寸链（PostgreSQL）</h2>
      <div class="chain-list">
        <div *ngFor="let c of chains" class="card chain-item"
             [class.active]="selected()?.id === c.id"
             (click)="select(c)">
          <div class="chain-code">{{ c.code }}</div>
          <div class="chain-name">{{ c.name }}</div>
          <div class="chain-desc">{{ c.description }}</div>
        </div>
      </div>
      <div class="error-box" *ngIf="loadError">{{ loadError }}</div>
    </div>

    <ng-container *ngIf="selected() as c">
      <div class="card">
        <h2 style="margin-top:0">{{ c.name }} — 组成环（封闭环：{{ c.closed_name }}）</h2>
        <table>
          <thead><tr>
            <th>key</th><th>尺寸</th><th>尺寸来源</th><th class="num">方向</th>
            <th class="num">公称</th><th class="num">es</th><th class="num">ei</th>
            <th>单位</th><th>分布假设</th><th>形态</th>
          </tr></thead>
          <tbody>
            <tr *ngFor="let r of c.rings">
              <td><code>{{ r.key }}</code></td>
              <td>{{ r.name }}</td>
              <td class="source">{{ r.source }}</td>
              <td class="num" [class.dir-pos]="r.direction === 1"
                  [class.dir-neg]="r.direction === -1">
                {{ r.direction === 1 ? '+1' : '−1' }}</td>
              <td class="num">{{ r.nominal }}</td>
              <td class="num">{{ r.es }}</td>
              <td class="num">{{ r.ei }}</td>
              <td>{{ r.unit }}</td>
              <td>
                <span class="tag" [class.warn]="r.distribution === 'unknown'">
                  {{ r.distribution }}
                  <ng-container *ngIf="r.dist_params['sigma']">
                    σ={{ r.dist_params['sigma'] }}</ng-container>
                </span>
              </td>
              <td>
                <span class="tag warn" *ngIf="r.es === r.ei">零公差</span>
                <span class="tag warn"
                      *ngIf="r.es !== r.ei && (r.es === 0 || r.ei === 0)">单边</span>
                <span class="tag"
                      *ngIf="r.es !== r.ei && r.es !== 0 && r.ei !== 0">双向</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <div class="controls">
          <div>
            <label>随机种子（固定可复现）</label>
            <input type="number" [(ngModel)]="seed" />
          </div>
          <div>
            <label>蒙特卡洛样本数</label>
            <input type="number" [(ngModel)]="nSamples" min="1" />
          </div>
          <div>
            <label>RSS 的 k（σ 倍数）</label>
            <input type="number" [(ngModel)]="kSigma" min="0.1" step="0.5" />
          </div>
          <div>
            <button (click)="run(c)" [disabled]="loading()">
              {{ loading() ? '计算中…' : '运行三种分析' }}</button>
          </div>
        </div>
        <div class="error-box" *ngIf="analysisError">{{ analysisError }}</div>
      </div>

      <ng-container *ngIf="result() as a">
        <div class="grid3">
          <div class="card" *ngIf="a.results.worst_case as wc">
            <app-worst-case [data]="wc"></app-worst-case>
          </div>
          <div class="card" *ngIf="a.results.rss as rs">
            <app-rss [data]="rs"></app-rss>
          </div>
          <div class="card"
               *ngIf="a.results.monte_carlo as mc; else mcBlocked">
            <app-monte-carlo [data]="mc"></app-monte-carlo>
          </div>
          <ng-template #mcBlocked>
            <div class="card method-card">
              <h3>③ 蒙特卡洛（固定种子抽样）</h3>
              <div class="error-box">{{ a.method_errors['monte_carlo']
                || '未运行' }}</div>
            </div>
          </ng-template>
        </div>

        <div class="card" *ngIf="!a.results.rss">
          <div class="error-box">{{ a.method_errors['rss'] }}</div>
        </div>

        <div class="card">
          <h3 style="margin-top:0">三种方法的前提对比</h3>
          <table>
            <thead><tr><th>方法</th><th>给出什么</th><th>前提</th></tr></thead>
            <tbody>
              <tr>
                <td><strong>极值法</strong></td>
                <td>保证界限 gap_min/gap_max（100% 互换）</td>
                <td>所有组成环同时达到最不利极限；不需要分布</td>
              </tr>
              <tr>
                <td><strong>RSS</strong></td>
                <td>均值、标准差、±kσ 区间</td>
                <td>独立、过程受控、每个环分布已知；不是保证界限</td>
              </tr>
              <tr>
                <td><strong>蒙特卡洛</strong></td>
                <td>经验分布、分位数、干涉比例、主导贡献</td>
                <td>按显式分布抽样；固定种子可复现；假设错误则结果错误</td>
              </tr>
            </tbody>
          </table>
          <p class="disclaimer">{{ a.disclaimer }}</p>
        </div>
      </ng-container>
    </ng-container>
  </div>
  `,
})
export class AppComponent implements OnInit {
  chains: Chain[] = [];
  selected = signal<Chain | null>(null);
  result = signal<AnalysisResult | null>(null);
  loading = signal(false);
  loadError = '';
  analysisError = '';

  seed = 20261006;
  nSamples = 100_000;
  kSigma = 3.0;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.api.listChains().subscribe({
      next: (list) => {
        this.chains = list;
        if (list.length) this.select(list[0]);
      },
      error: () => this.loadError = '无法连接后端 API（FastAPI :8000）',
    });
  }

  select(c: Chain): void {
    this.selected.set(c);
    this.result.set(null);
    this.analysisError = '';
  }

  run(c: Chain): void {
    this.loading.set(true);
    this.analysisError = '';
    this.api.analyze(c.id, this.seed, this.nSamples, this.kSigma)
      .subscribe({
        next: (run: Run) => this.result.set(run.result),
        error: (e: Error) => this.analysisError = e.message,
      })
      .add(() => this.loading.set(false));
  }
}
