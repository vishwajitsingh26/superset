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

/**
 * One region stage A found in the design, as published on its
 * `stage_complete` event. `bbox` is normalized (0-1) against the image it was
 * read from -- `source_image` says which, for a design uploaded as more than
 * one file/page.
 */
export type Region = {
  region_id?: string;
  title?: string | null;
  role?: string;
  source_image?: number;
  bbox?: { x: number; y: number; w: number; h: number };
};

export type StageEvent = {
  type:
    | 'stage_start'
    | 'stage_complete'
    | 'tool_call'
    | 'chart_done'
    | 'plugin_built'
    | 'plugin_group_split'
    | 'registry_rebuilt'
    | 'frontend_restarted'
    | 'frontend_restart_needed'
    | 'awaiting_input'
    | 'input_received'
    | 'cancelled'
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
  kind?: string;
  plan?: unknown[];
  fidelity_notes?: unknown[];
  ref?: string;
  viz_type?: string;
  ok?: boolean;
  detail?: string;
  cost?: number;
  regions?: Region[];
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

type RunState = 'idle' | 'uploading' | 'running' | 'waiting' | 'done' | 'error';

/**
 * One region in the stage A / stage B gate's tree, nested the way it will be
 * built. `plugin_choice` is `null` on a wrapper -- only a leaf is ever built
 * as a plugin -- and carries stage A's own reading only as a starting point:
 * the user's choice always wins, nothing here is a default that gets sent
 * unchosen.
 */
export type GateRegionNode = {
  region_id: string;
  n?: number;
  title?: string | null;
  role?: string;
  composition?: string;
  behavior?: string;
  plugin_choice?: {
    options: string[];
    /** A registered viz type stage A matched this region against, or `null`.
     * Information, not a default -- neither option is pre-selected either
     * way, see `note`. */
    stock_candidate?: string | null;
    /** Neutral: states what stage A found (or didn't) with no "recommends"
     * language, so it cannot read as a suggested answer. */
    note?: string;
  } | null;
  question_ids?: string[];
  children?: GateRegionNode[];
};

/** What the run is blocked on. Only ever set while planning. */
export type PendingAsk = {
  kind: 'questions' | 'plan' | 'datasets' | 'plugins' | 'region_review';
  label?: string;
  dashboard_title?: string | null;
  /** The stage A/B gate's region tree (`kind: 'region_review'` only). */
  regions?: GateRegionNode[];
  /** Sample tables the run proposes to write. Approved before anything else. */
  datasets?: {
    name: string;
    kind: 'derived' | 'placeholder';
    reason?: string;
    rows?: unknown[];
    region_ids?: string[];
  }[];
  options?: string[];
  questions?: {
    id: string;
    /** Stage C's shape. The gate (`kind: 'region_review'`) uses `text`
     * instead -- it has no options to pick from, only a free-text answer. */
    question?: string;
    why_it_matters?: string;
    /** Set when the build cannot proceed without an answer. */
    why_blocking?: string;
    region_id?: string;
    topic?: string;
    options?: string[];
    default?: string;
    /** The gate's shape: a free-text prompt and which stage B gap it closes
     * (see `gate_a.py`'s `GAP_*` constants) -- shown so the user knows what
     * an answer is for, not just what it is. */
    text?: string;
    gap?: string;
  }[];
  /** What stage F will build, one entry per distinct component. */
  entries?: {
    key: string;
    kind: string;
    title: string;
    viz_type?: string | null;
    what: string;
    rationale?: string;
    /** Only set on a `reuse` entry: what `get_chart_info` actually confirmed
     * about the existing chart, or (if no lookup was attached) stage C's own
     * unverified account of the match -- what the user checks a reuse
     * against, not just the plan to trust it. */
    reuse_evidence?: string;
    fidelity_loss?: string;
    used_by: { region_id: string; title: string }[];
    queries: number;
    query_note?: string;
    dataset?: string;
    draws_data?: boolean;
    crop?: string | null;
  }[];
  dropped?: { region_id: string; title: string; why?: string }[];
  /** Prefix a crop filename is appended to; the run's own session path. */
  crop_url?: string;
  /** False on the last round: the plan can no longer be sent back. */
  can_revise?: boolean;
  /**
   * A step is either the four fields split out, or one written line. Stage C
   * is asked for the split form, but a model that writes the same content as
   * prose is still describing the work, and a step that cannot be read is
   * worse than one that is not broken up.
   */
  plan?: (
    | string
    | {
        step?: number;
        what?: string;
        why?: string;
        exactness?: string;
        cost?: string;
      }
  )[];
  counts?: Record<string, number>;
};

export const ENDPOINT = '/api/v1/design_to_dashboard';
const ROUTE = '/design-to-dashboard';

/** The design image at this index, as a plain URL a browser `<img>` can
 * fetch directly -- same pattern as a plan step's `crop_url`. Works after a
 * reload with no local `File` object to build a blob URL from, since the
 * file lives on the server for the life of the session, not the tab. */
export function assetUrl(sessionId: string, index = 0): string {
  return `${ENDPOINT}/session/${sessionId}/asset/${index}/`;
}

/** The run id in the address bar, or null when this is a fresh page. */
export function sessionIdFromUrl(): string | null {
  const [, id] =
    window.location.pathname.match(/design-to-dashboard\/([^/?#]+)/) ?? [];
  return id || null;
}

/** Put the run in the address bar without adding a history entry.
 *
 * `replaceState` rather than `pushState`: a run is one page, so the back
 * button should leave the feature rather than step through its own stages.
 */
function showInUrl(id: string | null): void {
  const next = id ? `${ROUTE}/${id}/` : `${ROUTE}/`;
  if (window.location.pathname !== next) {
    window.history.replaceState(null, '', next);
  }
}

export function useDesignToDashboard() {
  const [events, setEvents] = useState<StageEvent[]>([]);
  const [state, setState] = useState<RunState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [thinking, setThinking] = useState('');
  const [thinkingStage, setThinkingStage] = useState('');
  const [pending, setPending] = useState<PendingAsk | null>(null);
  // What a reconnecting client uses to show the design it uploaded: there is
  // no local `File` object to build a blob URL from once the tab that chose
  // it is gone, only the server's own count of what this session holds.
  const [imageCount, setImageCount] = useState(0);
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
    setImageCount(0);
    showInUrl(null);
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

  // Attaching is separate from starting so a run can be picked up again:
  // the same poll drives a run this tab began and one it is only watching,
  // which is what makes a session id in the URL enough to continue from.
  const attach = useCallback(
    (id: string) => {
      stopPolling();
      cursorRef.current = 0;
      setEvents([]);
      setSessionId(id);
      showInUrl(id);
      if (!startedAtRef.current) startedAtRef.current = Date.now();
      setState('running');
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
              pending?: PendingAsk | null;
              events: StageEvent[];
              cursor?: number;
              thinking?: string;
              kind?: string;
              plan?: unknown[];
              fidelity_notes?: unknown[];
              thinking_stage?: string;
              images?: number;
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
            setPending(payload.pending ?? null);
            if (typeof payload.images === 'number') {
              setImageCount(payload.images);
            }
            if (payload.status === 'waiting') setState('waiting');
            else if (payload.status === 'running') setState('running');
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
            } else if (
              payload.status === 'interrupted' ||
              payload.status === 'cancelled'
            ) {
              // The worker that was driving this run is gone, so polling it
              // forever shows a page that looks live and answers nothing.
              // Stop, say so, and leave the user able to start again.
              setError(
                payload.status === 'cancelled'
                  ? 'This run was stopped.'
                  : 'This run was interrupted when the server restarted. Its ' +
                      'finished stages were saved, but it cannot be continued ' +
                      'from here yet.',
              );
              setState('error');
              stopPolling();
            }
          })
          .catch(() => {
            /* transient poll failure: keep going, the next tick may succeed */
          });
      }, 900);
    },
    [stopPolling],
  );

  // A run named in the address bar is picked up on load, which is what makes
  // the link shareable and what lets a reload land back in the same run
  // instead of an empty page. Runs once: `attach` then owns the id.
  const attachedRef = useRef(false);
  useEffect(() => {
    if (attachedRef.current) return;
    const existing = sessionIdFromUrl();
    if (existing) {
      attachedRef.current = true;
      attach(existing);
    }
  }, [attach]);

  const start = useCallback(
    async (files: File[], requirement: string) => {
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

        // Uploaded one at a time and in order: the endpoint names them
        // design_0, design_1 … and stage A refers to them by that index.
        for (const file of files) {
          const body = new FormData();
          body.append('file', file);
          // eslint-disable-next-line no-await-in-loop
          await SupersetClient.post({
            endpoint: `${ENDPOINT}/session/${id}/asset/`,
            postPayload: body,
          });
        }

        await SupersetClient.post({
          endpoint: `${ENDPOINT}/session/${id}/run/`,
          jsonPayload: { requirement },
        });

        setState('running');
        startedAtRef.current = Date.now();
        attach(id);
      } catch (caught) {
        const detail =
          caught instanceof Error ? caught.message : 'Could not start the run.';
        setError(detail);
        setState('error');
      }
    },
    [attach],
  );

  const reply = useCallback(
    async (answer: Record<string, unknown>) => {
      if (!sessionId) return;
      // Optimistically clear so the form cannot be submitted twice while the
      // worker wakes up; the next poll restores it if something went wrong.
      setPending(null);
      setState('running');
      await SupersetClient.post({
        endpoint: `${ENDPOINT}/session/${sessionId}/reply/`,
        jsonPayload: answer,
      });
    },
    [sessionId],
  );

  return {
    events,
    state,
    pending,
    reply,
    error,
    sessionId,
    imageCount,
    elapsed,
    thinking,
    thinkingStage,
    start,
    resume: attach,
    reset,
  };
}
