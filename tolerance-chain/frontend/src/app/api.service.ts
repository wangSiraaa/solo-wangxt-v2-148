import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, catchError, throwError } from 'rxjs';
import { AnalysisResult, Chain, Run } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = '/api';

  constructor(private http: HttpClient) {}

  listChains(): Observable<Chain[]> {
    return this.http.get<Chain[]>(`${this.base}/chains`);
  }

  analyze(
    chainId: number,
    seed: number,
    nSamples: number,
    kSigma: number,
  ): Observable<Run> {
    return this.http
      .post<Run>(`${this.base}/chains/${chainId}/analyze`, {
        seed, n_samples: nSamples, k_sigma: kSigma,
        methods: ['worst_case', 'rss', 'monte_carlo'],
      })
      .pipe(catchError((e: HttpErrorResponse) =>
        throwError(() => new Error(typeof e.error?.detail === 'string'
          ? e.error.detail : '分析请求失败'))));
  }
}
