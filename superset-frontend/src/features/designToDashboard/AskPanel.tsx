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
import { useMemo, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { styled } from '@apache-superset/core/theme';
import { PendingAsk } from './useDesignToDashboard';

const Block = styled.div`
  ${({ theme }) => `
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit * 3}px;
  `}
`;

const Question = styled.div`
  ${({ theme }) => `
    padding-bottom: ${theme.sizeUnit * 3}px;
    border-bottom: 1px solid ${theme.colorBorderSecondary};
    &:last-of-type { border-bottom: none; padding-bottom: 0; }
  `}
`;

const Ask = styled.div`
  ${({ theme }) => `
    color: ${theme.colorText};
    margin-bottom: ${theme.sizeUnit}px;
  `}
`;

const Why = styled.div`
  ${({ theme }) => `
    font-size: ${theme.fontSizeSM}px;
    color: ${theme.colorTextTertiary};
    margin-bottom: ${theme.sizeUnit * 2}px;
  `}
`;

const Choices = styled.div`
  ${({ theme }) => `
    display: flex;
    flex-wrap: wrap;
    gap: ${theme.sizeUnit * 2}px;
  `}
`;

const Choice = styled.button<{ selected: boolean }>`
  ${({ theme, selected }) => `
    padding: ${theme.sizeUnit}px ${theme.sizeUnit * 3}px;
    border-radius: ${theme.borderRadius * 4}px;
    cursor: pointer;
    font-size: ${theme.fontSizeSM}px;
    border: 1px solid ${selected ? theme.colorPrimary : theme.colorBorder};
    background-color: ${selected ? theme.colorPrimaryBg : 'transparent'};
    color: ${selected ? theme.colorPrimaryText : theme.colorText};
  `}
`;

const FreeText = styled.input`
  ${({ theme }) => `
    flex: 1;
    min-width: ${theme.sizeUnit * 40}px;
    padding: ${theme.sizeUnit}px ${theme.sizeUnit * 2}px;
    border: 1px solid ${theme.colorBorder};
    border-radius: ${theme.borderRadius}px;
    background: transparent;
    color: ${theme.colorText};
    font-size: ${theme.fontSizeSM}px;
  `}
`;

const Steps = styled.ol`
  ${({ theme }) => `
    margin: 0;
    padding-left: ${theme.sizeUnit * 4}px;
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit * 3}px;
  `}
`;

const StepWhat = styled.div`
  ${({ theme }) => `
    color: ${theme.colorText};
    font-weight: ${theme.fontWeightStrong};
  `}
`;

const StepLine = styled.div<{ tone?: 'warn' }>`
  ${({ theme, tone }) => `
    font-size: ${theme.fontSizeSM}px;
    color: ${tone === 'warn' ? theme.colorWarningText : theme.colorTextSecondary};
  `}
`;

const Actions = styled.div`
  ${({ theme }) => `
    display: flex;
    gap: ${theme.sizeUnit * 2}px;
    align-items: center;
    flex-wrap: wrap;
  `}
`;

const Primary = styled.button`
  ${({ theme }) => `
    padding: ${theme.sizeUnit * 2}px ${theme.sizeUnit * 4}px;
    border-radius: ${theme.borderRadius}px;
    border: 1px solid ${theme.colorPrimary};
    background-color: ${theme.colorPrimary};
    color: ${theme.colorWhite};
    font-weight: ${theme.fontWeightStrong};
    cursor: pointer;
    &:disabled { opacity: 0.45; cursor: not-allowed; }
  `}
`;

const Secondary = styled.button`
  ${({ theme }) => `
    padding: ${theme.sizeUnit * 2}px ${theme.sizeUnit * 3}px;
    border-radius: ${theme.borderRadius}px;
    border: 1px solid ${theme.colorBorder};
    background: none;
    color: ${theme.colorText};
    cursor: pointer;
    &:disabled { opacity: 0.45; cursor: not-allowed; }
  `}
`;

const Card = styled.li`
  ${({ theme }) => `
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit}px;
  `}
`;

const Shot = styled.img`
  ${({ theme }) => `
    max-width: 100%;
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadius}px;
    margin: ${theme.sizeUnit}px 0;
  `}
`;

const Tag = styled.span<{ tone?: 'new' | 'muted' }>`
  ${({ theme, tone }) => `
    display: inline-block;
    padding: 0 ${theme.sizeUnit}px;
    margin-right: ${theme.sizeUnit}px;
    border-radius: ${theme.borderRadius}px;
    font-size: ${theme.fontSizeSM}px;
    background-color: ${
      tone === 'new' ? theme.colorPrimaryBg : theme.colorBgTextHover
    };
    color: ${tone === 'new' ? theme.colorPrimaryText : theme.colorTextSecondary};
  `}
`;

type Props = {
  pending: PendingAsk;
  onReply: (answer: Record<string, unknown>) => void;
};

export default function AskPanel({ pending, onReply }: Props) {
  const questions = useMemo(() => pending.questions ?? [], [pending.questions]);
  // Pre-select each recommended default so answering is a scan, not a form.
  const [answers, setAnswers] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      questions.map(q => [q.id, q.default ?? q.options?.[0] ?? '']),
    ),
  );
  const [feedback, setFeedback] = useState('');
  // Per-plugin notes for the stage F review, keyed by entry.
  const [notes, setNotes] = useState<Record<string, string>>({});

  if (pending.kind === 'datasets') {
    const datasets = pending.datasets ?? [];
    const [accept, decline] = pending.options ?? [];
    return (
      <Block data-test="d2d-dataset-approval">
        {pending.label && <Ask>{pending.label}</Ask>}
        <Steps>
          {datasets.map(dataset => (
            <li key={dataset.name}>
              <StepWhat>{dataset.name}</StepWhat>
              <StepLine tone="warn">
                {t(
                  '%s sample row(s), written as a real table',
                  String(dataset.rows?.length ?? 0),
                )}
              </StepLine>
              {dataset.reason && <StepLine>{dataset.reason}</StepLine>}
            </li>
          ))}
        </Steps>
        <Actions>
          <Primary type="button" onClick={() => onReply({ approved: true })}>
            {accept ?? t('Create the sample tables')}
          </Primary>
          <Secondary type="button" onClick={() => onReply({ approved: false })}>
            {decline ?? t('Stop')}
          </Secondary>
          <StepLine>
            {t(
              'Every number in these tables is read off the design, not your data.',
            )}
          </StepLine>
        </Actions>
      </Block>
    );
  }

  if (pending.kind === 'plugins') {
    const entries = pending.entries ?? [];
    const dropped = pending.dropped ?? [];
    const counts = pending.counts ?? {};
    return (
      <Block data-test="d2d-plugin-review">
        {pending.label && <Ask>{pending.label}</Ask>}
        <Why>
          {t(
            '%s plugin(s) for %s section(s), %s quer(ies) each time the dashboard loads.',
            String(counts.plugins ?? 0),
            String(counts.regions_covered ?? 0),
            String(counts.queries_per_load ?? 0),
          )}
        </Why>
        <Steps>
          {entries.map(entry => (
            <Card key={entry.key}>
              <StepWhat>
                <Tag tone={entry.kind === 'new_plugin' ? 'new' : 'muted'}>
                  {entry.kind === 'new_plugin' ? t('NEW') : entry.kind}
                </Tag>
                {entry.title}
              </StepWhat>
              {entry.crop && pending.crop_url && (
                <Shot
                  src={`${pending.crop_url}${entry.crop}`}
                  alt={entry.title}
                  loading="lazy"
                />
              )}
              <StepLine>
                {entry.what}
                {entry.viz_type ? ` — ${entry.viz_type}` : ''}
              </StepLine>
              <StepLine>
                {entry.used_by.length > 1
                  ? t(
                      'Built once, used by %s sections: %s',
                      String(entry.used_by.length),
                      entry.used_by.map(u => u.title).join(', '),
                    )
                  : t('Used by %s', entry.used_by[0]?.title ?? '')}
              </StepLine>
              <StepLine>
                {t('%s quer(ies) per load', String(entry.queries))}
                {entry.query_note ? ` — ${entry.query_note}` : ''}
              </StepLine>
              <StepLine tone={entry.draws_data ? undefined : 'warn'}>
                {t('Data')}: {entry.dataset}
              </StepLine>
              {entry.fidelity_loss && (
                <StepLine tone="warn">
                  {t('Will differ')}: {entry.fidelity_loss}
                </StepLine>
              )}
              {entry.kind === 'new_plugin' && (
                <FreeText
                  value={notes[entry.key] ?? ''}
                  placeholder={t('Anything to change about this one?')}
                  onChange={e =>
                    setNotes(prev => ({ ...prev, [entry.key]: e.target.value }))
                  }
                />
              )}
            </Card>
          ))}
        </Steps>
        {dropped.length > 0 && (
          <StepLine tone="warn">
            {t('Not being built: %s', dropped.map(d => d.title).join(', '))}
          </StepLine>
        )}
        <Actions>
          <Primary
            type="button"
            onClick={() => onReply({ approved: true, notes })}
          >
            {t('Build these')}
          </Primary>
          <Secondary
            type="button"
            onClick={() => onReply({ approved: false, feedback })}
          >
            {t('Cancel the run')}
          </Secondary>
          <StepLine>
            {t(
              'Notes go to the plugin they sit under. To change what gets built, send the plan back a step.',
            )}
          </StepLine>
        </Actions>
      </Block>
    );
  }

  if (pending.kind === 'plan') {
    const steps = pending.plan ?? [];
    return (
      <Block data-test="d2d-plan-approval">
        {steps.length === 0 && (
          <StepLine>{t('No steps were described for this plan.')}</StepLine>
        )}
        <Steps>
          {steps.map(step => (
            <li key={step.step}>
              <StepWhat>{step.what}</StepWhat>
              {step.why && <StepLine>{step.why}</StepLine>}
              {step.exactness && (
                <StepLine tone="warn">
                  {t('Match')}: {step.exactness}
                </StepLine>
              )}
              {step.cost && (
                <StepLine>
                  {t('Cost')}: {step.cost}
                </StepLine>
              )}
            </li>
          ))}
        </Steps>
        <FreeText
          value={feedback}
          placeholder={
            pending.can_revise
              ? t('What should change? Say so and it will plan again.')
              : t('Optional: why you are rejecting this')
          }
          onChange={e => setFeedback(e.target.value)}
        />
        <Actions>
          <Primary
            type="button"
            onClick={() => onReply({ approved: true, feedback })}
          >
            {t('Approve and build')}
          </Primary>
          {pending.can_revise && (
            <Secondary
              type="button"
              disabled={!feedback.trim()}
              onClick={() => onReply({ approved: false, feedback })}
            >
              {t('Send back with changes')}
            </Secondary>
          )}
          <Secondary
            type="button"
            onClick={() => onReply({ approved: false, feedback: '' })}
          >
            {t('Cancel the run')}
          </Secondary>
          <StepLine>
            {pending.can_revise
              ? t(
                  'Nothing is created until you approve. Say what is wrong and it will re-plan.',
                )
              : t('Nothing is created until you approve.')}
          </StepLine>
        </Actions>
      </Block>
    );
  }

  // Blocking questions first: an unanswered one leaves a section that cannot
  // be built, so it should not be the tenth thing read.
  const ordered = [
    ...questions.filter(q => q.why_blocking),
    ...questions.filter(q => !q.why_blocking),
  ];
  const blockingCount = questions.filter(q => q.why_blocking).length;
  const answered = ordered.filter(q => (answers[q.id] ?? '').trim()).length;
  const unansweredBlocking = ordered.filter(
    q => q.why_blocking && !(answers[q.id] ?? '').trim(),
  ).length;

  return (
    <Block data-test="d2d-questions">
      <StepLine>
        {t('%s of %s answered', String(answered), String(ordered.length))}
        {blockingCount > 0 &&
          ` · ${t('%s block the build', String(blockingCount))}`}
      </StepLine>
      {ordered.map(q => (
        <Question key={q.id}>
          {(q.why_blocking || q.region_id) && (
            <StepLine tone={q.why_blocking ? 'warn' : undefined}>
              {q.why_blocking ? `${t('Blocks the build')} · ` : ''}
              {q.region_id ?? q.topic ?? ''}
            </StepLine>
          )}
          <Ask>{q.question}</Ask>
          {q.why_blocking && <Why>{q.why_blocking}</Why>}
          {q.why_it_matters && <Why>{q.why_it_matters}</Why>}
          <Choices>
            {(q.options ?? []).map(option => (
              <Choice
                key={option}
                type="button"
                selected={answers[q.id] === option}
                onClick={() => setAnswers({ ...answers, [q.id]: option })}
              >
                {option}
              </Choice>
            ))}
            <FreeText
              value={
                (q.options ?? []).includes(answers[q.id])
                  ? ''
                  : (answers[q.id] ?? '')
              }
              placeholder={t('or type your own answer')}
              onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })}
            />
          </Choices>
        </Question>
      ))}
      <Actions>
        <Primary
          type="button"
          disabled={unansweredBlocking > 0}
          onClick={() => onReply({ answers })}
        >
          {t('Send answers')}
        </Primary>
        <StepLine tone={unansweredBlocking > 0 ? 'warn' : undefined}>
          {unansweredBlocking > 0
            ? t(
                '%s question(s) block the build and need an answer.',
                String(unansweredBlocking),
              )
            : t('Defaults are pre-selected — send as-is to accept them.')}
        </StepLine>
      </Actions>
    </Block>
  );
}
