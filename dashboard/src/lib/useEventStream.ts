import { useEffect, useRef, useState } from 'react';
import type { Ev } from './types';

export const EVENT_TYPES = [
  'message.received', 'persona.reply', 'scam.detected', 'intel.extracted', 'case.summary', 'transcript.partial',
  'transcript.final', 'call.status', 'metrics.speed', 'ratelimit.status', 'task.retrying', 'network.updated',
];

/** SSE on the same origin. EventSource reconnects by itself and replays with Last-Event-ID. */
export function useEventStream(onEvent: (ev: Ev) => void) {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onEvent);
  handler.current = onEvent;
  useEffect(() => {
    let es: EventSource | null = null;
    let timer: number | undefined;
    let closed = false;
    const open = () => {
      es = new EventSource('/api/v1/events/stream');
      es.onopen = () => setConnected(true);
      es.onerror = () => {
        setConnected(false);
        if (es && es.readyState === EventSource.CLOSED && !closed) {
          es.close();
          timer = window.setTimeout(open, 3000);
        }
      };
      for (const t of EVENT_TYPES) {
        es.addEventListener(t, (msg) => {
          try {
            handler.current(JSON.parse((msg as MessageEvent).data));
          } catch {
            /* ignore malformed event */
          }
        });
      }
    };
    open();
    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      es?.close();
    };
  }, []);
  return connected;
}
