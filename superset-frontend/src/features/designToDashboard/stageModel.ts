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
import { StageEvent } from './useDesignToDashboard';

export type StageStatus = 'pending' | 'running' | 'done' | 'failed';

export type Stage = {
  key: string;
  title: string;
  status: StageStatus;
  summary?: string;
  thinking?: string;
  cost?: number;
  detail?: string[];
};

/** The pipeline's fixed shape, so pending steps are visible from the start. */
const STAGES: { key: string; title: string }[] = [
  { key: 'A', title: 'Read the design' },
  { key: 'B', title: 'Find matching data' },
  { key: 'clarify', title: 'Check for anything unclear' },
  { key: 'C', title: 'Choose chart types' },
  { key: 'F', title: 'Build custom chart plugins' },
  { key: 'D', title: 'Configure charts' },
  { key: 'E', title: 'Lay out the dashboard' },
  { key: 'apply', title: 'Create the dashboard' },
  { key: 'verify', title: 'Check it renders' },
];

export type Conversation = {
  stages: Stage[];
  result?: StageEvent;
  failure?: StageEvent;
  question?: StageEvent;
};

/**
 * Fold the event log into a stage list.
 *
 * Rendering events one-per-card made the panel read as a log rather than a
 * conversation; the pipeline has a known shape, so the events are folded onto
 * it instead.
 */
export function buildConversation(
  events: StageEvent[],
  liveThinking: string,
  liveStage: string,
): Conversation {
  const byKey = new Map<string, Stage>(
    STAGES.map(s => [s.key, { ...s, status: 'pending' as StageStatus }]),
  );
  let result: StageEvent | undefined;
  let failure: StageEvent | undefined;
  let question: StageEvent | undefined;

  events.forEach(event => {
    const key = event.stage ?? '';
    const stage = byKey.get(key);

    switch (event.type) {
      case 'stage_start':
        if (stage) stage.status = 'running';
        break;
      case 'stage_complete':
        if (stage) {
          stage.status = 'done';
          stage.summary = event.summary;
          stage.thinking = event.thinking;
          stage.cost = event.cost;
        }
        break;
      case 'tool_call': {
        const running = [...byKey.values()].find(s => s.status === 'running');
        if (running && event.tool) {
          running.detail = [
            ...(running.detail ?? []),
            `Looked up ${event.tool}`,
          ];
        }
        break;
      }
      case 'plugin_built':
      case 'frontend_restarted':
      case 'frontend_restart_needed':
      case 'registry_rebuilt': {
        const f = byKey.get('F');
        if (f && event.label) {
          f.detail = [...(f.detail ?? []), event.label];
        }
        break;
      }
      case 'chart_done': {
        const d = byKey.get('D');
        if (d && event.label) d.detail = [event.label];
        break;
      }
      case 'retry': {
        const running = [...byKey.values()].find(s => s.status === 'running');
        if (running) {
          running.detail = [
            ...(running.detail ?? []),
            event.label ?? 'Retrying',
          ];
        }
        break;
      }
      case 'needs_input':
      case 'needs_approval':
        question = event;
        break;
      case 'done': {
        const apply = byKey.get('apply');
        if (apply) apply.status = 'done';
        result = event;
        break;
      }
      case 'error': {
        const running = [...byKey.values()].find(s => s.status === 'running');
        if (running) running.status = 'failed';
        failure = event;
        break;
      }
      default:
        break;
    }
  });

  // Reasoning for the stage in flight has not been attached to an event yet.
  if (liveThinking) {
    const stage =
      byKey.get(liveStage) ??
      [...byKey.values()].find(s => s.status === 'running');
    if (stage) stage.thinking = liveThinking;
  }

  return { stages: [...byKey.values()], result, failure, question };
}
