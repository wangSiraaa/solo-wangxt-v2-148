import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Analysis, Chain } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  /** 通过 proxy.conf.json 转发到 FastAPI (8000) */
  private readonly base = '/api';

  listChains(): Observable<Chain[]> {
    return this.http.get<Chain[]>(`${this.base}/chains`);
  }

  getChain(id: number): Observable<Chain> {
    return this.http.get<Chain>(`${this.base}/chains/${id}`);
  }

  createChain(payload: Partial<Chain>): Observable<Chain> {
    return this.http.post<Chain>(`${this.base}/chains`, payload);
  }

  deleteChain(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/chains/${id}`);
  }

  analyze(id: number, nSamples?: number, seed?: number): Observable<Analysis> {
    return this.http.post<Analysis>(
      `${this.base}/chains/${id}/analyze`,
      { n_samples: nSamples ?? null, seed: seed ?? null },
    );
  }

  seedDemo(): Observable<{ created: { id: number; name: string }[] }> {
    return this.http.post<{ created: { id: number; name: string }[] }>(`${this.base}/demo/seed`, {});
  }

  thermalTerm(payload: {
    alpha_per_c: number;
    length_mm: number;
    delta_t_c: number;
    delta_t_lower_c: number | null;
    delta_t_upper_c: number | null;
    uncertainty_kind: 'uniform' | 'triangular' | 'unknown';
  }): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(`${this.base}/utils/thermal-expansion-term`, payload);
  }
}
