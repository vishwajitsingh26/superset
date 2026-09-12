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
import { ChangeEvent, useEffect, useRef, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { styled } from '@apache-superset/core/theme';
import { buildConversation, Stage } from './stageModel';
import AskPanel from './AskPanel';
import { PendingAsk, StageEvent } from './useDesignToDashboard';

const Wrap = styled.div`
  ${({ theme }) => `
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: ${theme.sizeUnit * 3}px;
  `}
`;

const Thread = styled.div`
  ${({ theme }) => `
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit * 4}px;
    padding-right: ${theme.sizeUnit}px;
  `}
`;

const Turn = styled.div<{ from: 'user' | 'agent' }>`
  ${({ from }) => `
    display: flex;
    justify-content: ${from === 'user' ? 'flex-end' : 'flex-start'};
  `}
`;

const Bubble = styled.div<{ from: 'user' | 'agent' }>`
  ${({ theme, from }) => `
    max-width: ${from === 'user' ? '80%' : '100%'};
    width: ${from === 'user' ? 'auto' : '100%'};
    border-radius: ${theme.borderRadius * 3}px;
    padding: ${theme.sizeUnit * 3}px ${theme.sizeUnit * 4}px;
    background-color: ${
      from === 'user' ? theme.colorPrimaryBg : theme.colorBgContainer
    };
    border: 1px solid ${
      from === 'user' ? theme.colorPrimaryBorder : theme.colorBorderSecondary
    };
    color: ${theme.colorText};
  `}
`;

const Who = styled.div`
  ${({ theme }) => `
    font-size: ${theme.fontSizeSM}px;
    color: ${theme.colorTextTertiary};
    margin-bottom: ${theme.sizeUnit}px;
  `}
`;

const Steps = styled.ol`
  ${({ theme }) => `
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit * 2}px;
  `}
`;

const Step = styled.li<{ status: string }>`
  ${({ theme, status }) => `
    display: grid;
    grid-template-columns: ${theme.sizeUnit * 5}px 1fr;
    gap: ${theme.sizeUnit * 2}px;
    opacity: ${status === 'pending' ? 0.45 : 1};
  `}
`;

const Mark = styled.span<{ status: string }>`
  ${({ theme, status }) => `
    line-height: ${theme.sizeUnit * 5}px;
    color: ${
      status === 'done'
        ? theme.colorSuccess
        : status === 'failed'
          ? theme.colorError
          : status === 'running'
            ? theme.colorPrimary
            : theme.colorTextQuaternary
    };
  `}
`;

const StepTitle = styled.div<{ status: string }>`
  ${({ theme, status }) => `
    font-weight: ${
      status === 'running' ? theme.fontWeightStrong : theme.fontWeightNormal
    };
    color: ${theme.colorText};
  `}
`;

const StepMeta = styled.div`
  ${({ theme }) => `
    font-size: ${theme.fontSizeSM}px;
    color: ${theme.colorTextSecondary};
  `}
`;

const Reasoning = styled.div`
  ${({ theme }) => `
    margin-top: ${theme.sizeUnit}px;
    padding: ${theme.sizeUnit * 2}px ${theme.sizeUnit * 3}px;
    border-left: 2px solid ${theme.colorBorder};
    background-color: ${theme.colorFillQuaternary};
    border-radius: 0 ${theme.borderRadius}px ${theme.borderRadius}px 0;
    max-height: ${theme.sizeUnit * 40}px;
    overflow-y: auto;
    white-space: pre-wrap;
    font-size: ${theme.fontSizeSM}px;
    line-height: 1.55;
    color: ${theme.colorTextSecondary};
  `}
`;

const Disclosure = styled.details`
  ${({ theme }) => `
    summary {
      cursor: pointer;
      color: ${theme.colorTextTertiary};
      font-size: ${theme.fontSizeSM}px;
      margin-top: ${theme.sizeUnit}px;
    }
  `}
`;

const Composer = styled.div`
  ${({ theme }) => `
    border: 1px solid ${theme.colorBorder};
    border-radius: ${theme.borderRadius * 2}px;
    padding: ${theme.sizeUnit * 3}px;
    background-color: ${theme.colorBgContainer};
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit * 2}px;
  `}
`;

const Textarea = styled.textarea`
  ${({ theme }) => `
    width: 100%;
    min-height: ${theme.sizeUnit * 14}px;
    resize: vertical;
    border: none;
    outline: none;
    padding: ${theme.sizeUnit}px 0;
    font-family: inherit;
    font-size: ${theme.fontSize}px;
    color: ${theme.colorText};
    background: transparent;
  `}
`;

const Row = styled.div`
  ${({ theme }) => `
    display: flex;
    align-items: center;
    gap: ${theme.sizeUnit * 2}px;
    flex-wrap: wrap;
  `}
`;

const Button = styled.button`
  ${({ theme }) => `
    padding: ${theme.sizeUnit * 2}px ${theme.sizeUnit * 4}px;
    border-radius: ${theme.borderRadius}px;
    border: 1px solid ${theme.colorPrimary};
    background-color: ${theme.colorPrimary};
    color: ${theme.colorWhite};
    cursor: pointer;
    font-weight: ${theme.fontWeightStrong};
    &:disabled { opacity: 0.45; cursor: not-allowed; }
  `}
`;

const Ghost = styled.button`
  ${({ theme }) => `
    padding: ${theme.sizeUnit * 2}px ${theme.sizeUnit * 3}px;
    border-radius: ${theme.borderRadius}px;
    border: 1px solid ${theme.colorBorder};
    background: none;
    color: ${theme.colorText};
    cursor: pointer;
  `}
`;

const Hint = styled.span`
  ${({ theme }) => `
    color: ${theme.colorTextTertiary};
    font-size: ${theme.fontSizeSM}px;
  `}
`;

const Thumb = styled.img`
  ${({ theme }) => `
    max-height: ${theme.sizeUnit * 20}px;
    border-radius: ${theme.borderRadius}px;
    border: 1px solid ${theme.colorBorderSecondary};
    display: block;
    margin-bottom: ${theme.sizeUnit}px;
  `}
`;

const MARK = { done: '✓', running: '◐', failed: '✕', pending: '○' } as const;

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m ? `${m}m ${s}s` : `${s}s`;
}

function StepRow({ stage }: { stage: Stage }) {
  const live = stage.status === 'running';
  return (
    <Step status={stage.status}>
      <Mark status={stage.status}>
        {MARK[stage.status as keyof typeof MARK]}
      </Mark>
      <div>
        <StepTitle status={stage.status}>{t(stage.title)}</StepTitle>
        {stage.summary && (
          <StepMeta>
            {stage.summary}
            {stage.cost ? ` · $${stage.cost.toFixed(2)}` : ''}
          </StepMeta>
        )}
        {stage.detail?.length ? (
          <StepMeta>{stage.detail[stage.detail.length - 1]}</StepMeta>
        ) : null}
        {stage.thinking && live && <Reasoning>{stage.thinking}</Reasoning>}
        {stage.thinking && !live && (
          <Disclosure>
            <summary>{t('Show reasoning')}</summary>
            <Reasoning>{stage.thinking}</Reasoning>
          </Disclosure>
        )}
      </div>
    </Step>
  );
}

type Props = {
  events: StageEvent[];
  state: string;
  elapsed: number;
  thinking: string;
  thinkingStage: string;
  pending: PendingAsk | null;
  onReply: (answer: Record<string, unknown>) => void;
  error: string | null;
  requirement: string;
  previewUrl: string | null;
  onStart: (files: File[], requirement: string) => void;
  onReset: () => void;
  onFileChosen: (files: File[]) => void;
  onRequirementChange: (value: string) => void;
};

export default function ChatPanel({
  events,
  state,
  elapsed,
  thinking,
  thinkingStage,
  pending,
  onReply,
  error,
  requirement,
  previewUrl,
  onStart,
  onReset,
  onFileChosen,
  onRequirementChange,
}: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const busy = state === 'running' || state === 'uploading';
  const waiting = state === 'waiting' && pending !== null;
  const started = busy || state === 'done' || state === 'error';

  const { stages, result, failure, question } = buildConversation(
    events,
    thinking,
    thinkingStage,
  );

  // Follow the newest content while a run is in flight.
  useEffect(() => {
    if (busy && threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [busy, events.length, thinking]);

  const choose = (e: ChangeEvent<HTMLInputElement>) => {
    const chosen = Array.from(e.target.files ?? []);
    setFiles(chosen);
    onFileChosen(chosen);
  };

  const totalCost = stages.reduce((sum, s) => sum + (s.cost ?? 0), 0);

  return (
    <Wrap>
      <Thread ref={threadRef}>
        {!started && (
          <Turn from="agent">
            <Bubble from="agent">
              <Who>{t('Design to Dashboard')}</Who>
              {t(
                'Share a Figma export or a screenshot of a dashboard and tell me what you need. ' +
                  'I will match it to your data, reuse charts where they exist, and build it.',
              )}
            </Bubble>
          </Turn>
        )}

        {started && (
          <Turn from="user">
            <Bubble from="user">
              {previewUrl && <Thumb src={previewUrl} alt={t('Your design')} />}
              {requirement || t('Rebuild this dashboard in Superset.')}
            </Bubble>
          </Turn>
        )}

        {started && (
          <Turn from="agent">
            <Bubble from="agent">
              <Who>
                {busy
                  ? `${t('Working')} · ${formatElapsed(elapsed)}`
                  : t('Finished')}
                {totalCost ? ` · $${totalCost.toFixed(2)}` : ''}
              </Who>
              <Steps>
                {stages.map(stage => (
                  <StepRow key={stage.key} stage={stage} />
                ))}
              </Steps>
            </Bubble>
          </Turn>
        )}

        {waiting && pending && (
          <Turn from="agent">
            <Bubble from="agent">
              <Who>
                {pending.kind === 'plan'
                  ? t('Review the plan')
                  : t('A few questions first')}
              </Who>
              <AskPanel pending={pending} onReply={onReply} />
            </Bubble>
          </Turn>
        )}

        {question && (
          <Turn from="agent">
            <Bubble from="agent">
              <Who>{t('I need your input')}</Who>
              {(question.questions ?? []).map((q, i) => (
                <div key={i}>• {(q as { question?: string }).question}</div>
              ))}
            </Bubble>
          </Turn>
        )}

        {result && (
          <Turn from="agent">
            <Bubble from="agent">
              <Who>{t('Done')}</Who>
              <a href={result.dashboard_url} target="_blank" rel="noreferrer">
                {t('Open dashboard')} #{result.dashboard_id}
              </a>
              {result.charts_created
                ? ` · ${result.charts_created.length} ${t('charts created')}`
                : ''}
            </Bubble>
          </Turn>
        )}

        {(failure || error) && (
          <Turn from="agent">
            <Bubble from="agent">
              <Who>{t('That did not work')}</Who>
              {failure?.detail ?? error}
            </Bubble>
          </Turn>
        )}
      </Thread>

      <Composer>
        {files.length > 0 && <Hint>{files.map(f => f.name).join(', ')}</Hint>}
        <Textarea
          value={requirement}
          placeholder={t(
            'What do you need? e.g. "Rebuild this sales dashboard, monthly, KPIs on top."',
          )}
          onChange={e => onRequirementChange(e.target.value)}
          disabled={busy}
        />
        <Row>
          <Ghost type="button" onClick={() => inputRef.current?.click()}>
            {files.length > 0 ? t('Change design') : t('Attach design')}
          </Ghost>
          <input
            ref={inputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,application/pdf"
            multiple
            hidden
            onChange={choose}
          />
          <Button
            type="button"
            disabled={files.length === 0 || busy}
            onClick={() => files.length > 0 && onStart(files, requirement)}
          >
            {busy ? t('Building…') : t('Build')}
          </Button>
          {(state === 'done' || state === 'error') && (
            <Ghost type="button" onClick={onReset}>
              {t('Start over')}
            </Ghost>
          )}
        </Row>
      </Composer>
    </Wrap>
  );
}
