import { useCallback, useEffect, useRef, useState } from 'react';
import type { CaseData, Ev, Health, Network } from './types';
import { useEventStream } from './useEventStream';

export interface Store {
  cases: Record<string, CaseData>;
  networks: Network[];
  health: Health | null;
  speed: Record<string, any>;
  ratelimit: Record<string, any>;
  connected: boolean;
  loaded: boolean;
  flashNetwork: string | null;
  refreshHealth: () => void;
}

async function getJSON(url: string) {
  const r = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(url + ' ' + r.status);
  return r.json();
}

function toCaseData(d: any): CaseData {
  return { case: d.case, messages: d.messages || [], intel: d.intel || [], events: d.events || [], evidence: d.evidence || [], partial: {} };
}

export function useStore(): Store {
  const [cases, setCases] = useState<Record<string, CaseData>>({});
  const [networks, setNetworks] = useState<Network[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [speed, setSpeed] = useState<Record<string, any>>({});
  const [ratelimit, setRatelimit] = useState<Record<string, any>>({});
  const [loaded, setLoaded] = useState(false);
  const [flashNetwork, setFlashNetwork] = useState<string | null>(null);
  const pending = useRef<Ev[]>([]);
  const fetching = useRef<Set<string>>(new Set());
  const ready = useRef(false);

  const loadCase = useCallback(async (id: string) => {
    if (fetching.current.has(id)) return;
    fetching.current.add(id);
    try {
      const d = await getJSON('/api/v1/cases/' + id);
      setCases((prev) => ({ ...prev, [id]: toCaseData(d) }));
    } catch {
      /* case not visible yet */
    } finally {
      fetching.current.delete(id);
    }
  }, []);

  const loadNetworks = useCallback(async () => {
    try {
      setNetworks(await getJSON('/api/networks'));
    } catch {
      /* keep the last list */
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const r = await fetch('/health');
      setHealth(await r.json());
    } catch {
      setHealth(null);
    }
  }, []);

  const apply = useCallback((ev: Ev) => {
    if (ev.type === 'metrics.speed') setSpeed((s) => ({ ...s, [ev.data.step]: { ...ev.data, ts: ev.ts } }));
    if (ev.type === 'ratelimit.status') setRatelimit((s) => ({ ...s, [ev.data.model]: ev.data }));
    if (ev.type === 'network.updated') {
      loadNetworks();
      setFlashNetwork(ev.data.network_id);
      window.setTimeout(() => setFlashNetwork(null), 3000);
    }
    const id = ev.case_id;
    if (!id) return;
    setCases((prev) => {
      const cd = prev[id];
      if (!cd) {
        loadCase(id);
        return prev;
      }
      if (ev.id != null && cd.events.some((e) => e.id === ev.id)) return prev;
      const next: CaseData = { ...cd, partial: { ...cd.partial } };
      if (ev.type !== 'transcript.partial' && ev.type !== 'ratelimit.status') next.events = [...cd.events, ev].slice(-1500);
      const d = ev.data || {};
      if ((ev.type === 'message.received' || ev.type === 'persona.reply') && d.message_id != null
          && !cd.messages.some((m) => m.id === d.message_id)) {
        next.messages = [...cd.messages, { id: d.message_id, case_id: id, role: ev.type === 'persona.reply' ? 'persona' : 'scammer', text: d.text, ts: ev.ts }];
      }
      if (ev.type === 'intel.extracted' && !cd.intel.some((i) => i.kind === d.kind && i.value === d.value)) {
        next.intel = [...cd.intel, { case_id: id, kind: d.kind, value: d.value, message_id: d.message_id, first_seen: ev.ts, source: d.source }];
      }
      if (ev.type === 'scam.detected' && d.stage === 'final' && d.verdict && d.verdict !== 'unknown' && !d.recheck) {
        next.case = { ...next.case, verdict: d.verdict, scam_type: d.scam_type || next.case.scam_type };
      }
      if (ev.type === 'case.summary') {
        next.case = { ...next.case, summary: d.summary || next.case.summary, status: d.status || next.case.status };
      }
      if (ev.type === 'transcript.partial') next.partial[d.speaker] = (next.partial[d.speaker] || '') + (d.delta || '');
      if (ev.type === 'transcript.final') next.partial[d.speaker] = '';
      next.case = { ...next.case, updated_at: ev.ts };
      return { ...prev, [id]: next };
    });
  }, [loadCase, loadNetworks]);

  const onEvent = useCallback((ev: Ev) => {
    if (!ready.current) pending.current.push(ev);
    else apply(ev);
  }, [apply]);

  const connected = useEventStream(onEvent);

  useEffect(() => {
    (async () => {
      try {
        const list = await getJSON('/api/v1/cases?limit=200');
        const ids: string[] = (list.cases || []).map((c: any) => c.id);
        const out: Record<string, CaseData> = {};
        for (let i = 0; i < ids.length; i += 6) {
          const batch = await Promise.all(ids.slice(i, i + 6).map((id) => getJSON('/api/v1/cases/' + id).catch(() => null)));
          batch.forEach((d) => { if (d) out[d.case.id] = toCaseData(d); });
        }
        setCases(out);
      } catch {
        /* empty dashboard until the API answers */
      }
      await loadNetworks();
      await refreshHealth();
      ready.current = true;
      setLoaded(true);
      const buffered = pending.current;
      pending.current = [];
      buffered.forEach(apply);
    })();
  }, [apply, loadNetworks, refreshHealth]);

  return { cases, networks, health, speed, ratelimit, connected, loaded, flashNetwork, refreshHealth };
}
