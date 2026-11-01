import { useMemo } from 'react';
import type { Store } from '../lib/store';
import { KIND_LABEL, formatTime } from '../lib/utils';
import { Empty, PageHeader, Panel } from '../components/Layout';
import { IntelCard } from '../components/IntelCard';

const GROUPS = [
  { title: 'UPI IDs', kinds: ['upi'] }, { title: 'Phone Numbers', kinds: ['phone'] },
  { title: 'Bank Accounts and IFSC', kinds: ['bank_account', 'ifsc', 'card'] }, { title: 'Links and APKs', kinds: ['url', 'apk'] },
  { title: 'Wallets and Handles', kinds: ['crypto_wallet', 'social_handle', 'email'] },
  { title: 'Names and References', kinds: ['name', 'organisation', 'employee_id', 'reference_code', 'amount'] },
];

export const Intelligence = ({ store }: { store: Store }) => {
  const rows = useMemo(() => Object.values(store.cases).flatMap((c) => c.intel.map((i) => ({ ...i, case_id: c.case.id, scam_type: c.case.scam_type })))
    .sort((a, b) => (b.first_seen || '').localeCompare(a.first_seen || '')), [store.cases]);
  return (
    <div>
      <PageHeader title="Intelligence" subtitle="Validated identifiers extracted from every scammer message." connected={store.connected} />
      {rows.length === 0 ? <Panel><Empty /></Panel> : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-6">
            {GROUPS.map((g) => (
              <Panel key={g.title} title={g.title} right={<span className="text-xs text-slate-400">{rows.filter((r) => g.kinds.includes(r.kind)).length}</span>}>
                <IntelCard items={rows.filter((r) => g.kinds.includes(r.kind))} max={20} />
              </Panel>
            ))}
          </div>
          <div className="bg-white rounded-[32px] shadow-soft border border-white/60 overflow-hidden">
            <div className="grid grid-cols-12 gap-4 p-6 border-b border-gray-100 text-xs font-bold text-gray-400 uppercase tracking-wider bg-gray-50/50">
              <div className="col-span-2">Type</div><div className="col-span-4">Value</div><div className="col-span-2">Source</div>
              <div className="col-span-2">Case</div><div className="col-span-2">First seen</div>
            </div>
            <div className="p-2 space-y-1 max-h-[480px] overflow-y-auto">
              {rows.map((r, i) => (
                <div key={r.case_id + r.kind + r.value + i} className="grid grid-cols-12 gap-4 p-4 items-center rounded-2xl hover:bg-gray-50 text-sm">
                  <div className="col-span-2"><span className="px-3 py-1 bg-gray-100 rounded-lg text-xs font-medium text-gray-600">{KIND_LABEL[r.kind] || r.kind}</span></div>
                  <div className="col-span-4 font-mono text-charcoal break-all">{r.value}</div>
                  <div className="col-span-2 text-xs text-gray-500">{r.source || 'n/a'}</div>
                  <div className="col-span-2 text-xs font-mono text-gray-500">{r.case_id}</div>
                  <div className="col-span-2 text-xs text-gray-400">{formatTime(r.first_seen)}</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
