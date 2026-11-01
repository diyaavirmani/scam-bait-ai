import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { CaseData, Ev } from './types';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const IST: Intl.DateTimeFormatOptions = { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };

export function formatTime(iso?: string) {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString('en-IN', IST) + ' IST';
}

export function formatDateTime(iso?: string) {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? '' : d.toLocaleString('en-IN', { ...IST, day: '2-digit', month: 'short' }) + ' IST';
}

export function seconds(ms?: number | null) {
  return typeof ms === 'number' ? (ms / 1000).toFixed(1) + ' s' : '';
}

export function pct(p?: number | null) {
  return typeof p === 'number' ? Math.round(p * 100) + '%' : 'n/a';
}

export function mask(value: string) {
  return value.length <= 4 ? value : '*'.repeat(Math.min(value.length - 4, 8)) + value.slice(-4);
}

export const KIND_LABEL: Record<string, string> = {
  upi: 'UPI', phone: 'Phone', bank_account: 'Bank account', ifsc: 'IFSC', card: 'Card', url: 'Link', apk: 'APK',
  email: 'Email', crypto_wallet: 'Wallet', social_handle: 'Handle', name: 'Name', employee_id: 'Employee ID',
  organisation: 'Organisation', amount: 'Amount', reference_code: 'Reference',
};

export function deciderLabel(decidedBy?: string) {
  if (!decidedBy) return '';
  if (decidedBy.startsWith('cerebras')) return 'Cerebras qwen-3.8-27b';
  if (decidedBy === 'decisions') return 'OpenAI Decisions';
  if (decidedBy === 'regex') return 'Regex prefilter';
  return decidedBy;
}

/** Map each persona reply message id to the persona speed metric that preceded it (same case, event order). */
export function personaMeta(cd: CaseData): Record<number, { model?: string; ms?: number; provider?: string; degraded?: boolean }> {
  const out: Record<number, { model?: string; ms?: number; provider?: string; degraded?: boolean }> = {};
  let last: any = null;
  for (const e of cd.events) {
    if (e.type === 'metrics.speed' && e.data?.step === 'persona') last = e.data;
    if (e.type === 'persona.reply' && e.data?.message_id != null) {
      out[e.data.message_id] = { model: last?.model, ms: last?.ms, provider: last?.provider, degraded: !!e.data.degraded };
      last = null;
    }
  }
  return out;
}

export function detections(cd: CaseData): Ev[] {
  return cd.events.filter((e) => e.type === 'scam.detected');
}

export function lastReport(cd: CaseData): any {
  for (let i = cd.events.length - 1; i >= 0; i--) {
    const e = cd.events[i];
    if (e.type === 'case.summary' && e.data?.report) return e.data.report;
  }
  return null;
}

export function ncrpCategory(scamType: string) {
  if (!scamType || scamType === 'unknown' || scamType === 'not_a_scam') return 'Not classified yet';
  if (scamType === 'sextortion') return 'Online and Social Media Related Crime';
  return 'Online Financial Fraud';
}
