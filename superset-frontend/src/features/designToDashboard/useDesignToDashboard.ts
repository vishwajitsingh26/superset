/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { SupersetClient } from '@superset-ui/core';

export type StageEvent = {
  type:
    | 'stage_start'
    | 'stage_complete'
    | 'tool_call'
    | 'chart_done'
    | 'plugin_built'
    | 'registry_rebuilt'
    | 'frontend_restarted'
    | 'frontend_restart_needed'
    | 'retry'
    | 'needs_input'
    | 'needs_approval'
    | 'done'
    | 'error';
  stage?: string;
  label?: string;
  summary?: string;
  tool?: string;
  thinking?: string;
  ref?: string;
  viz_type?: string;
  ok?: boolean;
  detail?: string;
  cost?: number;
  regions?: unknown[];
  decisions?: unknown[];
  questions?: unknown[];
  adjustments?: unknown[];
  charts?: { ref: string; viz_type: string; ok: boolean }[];
  counts?: Record<string, number>;
  dashboard_id?: number;
  dashboard_url?: string;
  charts_created?: number[];
  cost_usd?: number;
  at?: number;
};

type RunState = 'idle' | 'uploading' | 'running' | 'done' | 'error';

const ENDPOINT = '/api/v1/design_to_dashboard';

export function useDesignToDashboard() {
  const [events, setEvents] = useState<StageEvent[]>([]);
  const [state, setState] = useState<RunState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [thinking, setThinking] = useState('');
  const [thinkingStage, setThinkingStage] = useState('');
  const cursorRef = useRef(0);
  const pollRef = useRef<number | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stopPolling();
    startedAtRef.current = null;
    setElapsed(0);
    setEvents([]);
    setError(null);
    setState('idle');
    setSessionId(null);
  }, [stopPolling]);

  // Drives the "still working" timer so a long stage never looks frozen.
  useEffect(() => {
    if (state !== 'running') return undefined;
    const tick = window.setInterval(() => {
      if (startedAtRef.current) {
        setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
      }
    }, 1000);
    return () => window.clearInterval(tick);
  }, [state]);

  useEffect(() => stopPolling, [stopPolling]);

  const start = useCallback(
    async (file: File, requirement: string) => {
      setEvents([]);
      setError(null);
      setState('uploading');
      try {
        const created = await SupersetClient.post({
          endpoint: `${ENDPOINT}/session/`,
          jsonPayload: {},
        });
        const { id } = created.json as { id: string };
        setSessionId(id);

        const body = new FormData();
        body.append('file', file);
        await SupersetClient.post({
          endpoint: `${ENDPOINT}/session/${id}/asset/`,
          postPayload: body,
        });

        await SupersetClient.post({
          endpoint: `${ENDPOINT}/session/${id}/run/`,
          jsonPayload: { requirement },
        });

        setState('running');
        startedAtRef.current = Date.now();
        // Polling rather than EventSource: the webpack dev-server proxy rewrites
        // response bodies, which buffers text/event-stream and leaves the request
        // pending forever. Polling the session endpoint works through any proxy.
        pollRef.current = window.setInterval(() => {
          SupersetClient.get({
            endpoint: `${ENDPOINT}/session/${id}/?since=${cursorRef.current}`,
          })
            .then(({ json }) => {
              const payload = json as {
                status: string;
                events: StageEvent[];
                cursor?: number;
                thinking?: string;
                thinking_stage?: string;
                error?: string | null;
              };
              // Only events after the cursor arrive, so append rather than
              // replace -- this is what lets the poll run fast enough for
              // reasoning to read as live.
              if (payload.events?.length) {
                setEvents(previous => [...previous, ...payload.events]);
              }
              if (typeof payload.cursor === 'number') {
                cursorRef.current = payload.cursor;
              }
              setThinking(payload.thinking ?? '');
              setThinkingStage(payload.thinking_stage ?? '');
              if (payload.status === 'done') {
                setState('done');
                stopPolling();
              } else if (payload.status === 'failed') {
                setError(payload.error ?? 'The run failed.');
                setState('error');
                stopPolling();
              } else if (payload.status === 'needs_input') {
                setState('done');
                stopPolling();
              }
            })
            .catch(() => {
              /* transient poll failure: keep going, the next tick may succeed */
            });
        }, 900);
      } catch (caught) {
        const detail =
          caught instanceof Error ? caught.message : 'Could not start the run.';
        setError(detail);
        setState('error');
      }
    },
    [stopPolling],
  );

  return {
    events,
    state,
    error,
    sessionId,
    elapsed,
    thinking,
    thinkingStage,
    start,
    reset,
  };
}
