import { ShieldAlert, User } from 'lucide-react';
import { cn, formatTime, seconds } from '../lib/utils';
import type { Msg } from '../lib/types';
import { Empty } from './Layout';

export interface FeedMsg extends Msg { meta?: { model?: string; ms?: number; provider?: string; degraded?: boolean }; }

export const PersonaBadge = ({ meta }: { meta?: FeedMsg['meta'] }) => {
  if (!meta) return null;
  if (meta.degraded) return <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-yellow-50 text-yellow-700 border border-yellow-200">fallback reply</span>;
  if (!meta.model) return null;
  const provider = meta.provider === 'openai' ? 'OpenAI' : 'Cerebras';
  const time = seconds(meta.ms);
  return (
    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-100">
      {provider} {meta.model}{time ? ', ' + time : ''}
    </span>
  );
};

export const LiveFeed = ({ messages, limit = 10 }: { messages: FeedMsg[]; limit?: number }) => {
  const shown = messages.slice(-limit);
  if (shown.length === 0) return <Empty />;
  return (
    <div className="h-full w-full overflow-y-auto space-y-3 pr-2 pb-2 flex flex-col">
      {shown.map((msg) => {
        const isScammer = msg.role === 'scammer';
        return (
          <div key={msg.case_id + msg.id} className={cn('flex gap-3 p-3 rounded-xl text-sm max-w-[90%]',
            isScammer ? 'bg-red-50 text-red-900 self-start mr-auto border border-red-100 shadow-sm'
              : 'bg-blue-50 text-blue-900 self-end ml-auto border border-blue-100 shadow-sm')}>
            <div className={cn('w-8 h-8 rounded-full flex items-center justify-center shrink-0 border',
              isScammer ? 'bg-white border-red-200 text-red-500' : 'bg-white border-blue-200 text-blue-500')}>
              {isScammer ? <ShieldAlert size={14} /> : <User size={14} />}
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-xs mb-1 opacity-70 flex flex-wrap items-center gap-2">
                <span>{isScammer ? 'Scammer' : 'Meena (persona)'}, {formatTime(msg.ts)}</span>
                {!isScammer && <PersonaBadge meta={msg.meta} />}
              </p>
              <p className="leading-relaxed text-slate-700 break-words">{msg.text}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
};
