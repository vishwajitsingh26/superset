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
          placeholder={t('Optional: what should change?')}
          onChange={e => setFeedback(e.target.value)}
        />
        <Actions>
          <Primary
            type="button"
            onClick={() => onReply({ approved: true, feedback })}
          >
            {t('Approve and build')}
          </Primary>
          <Secondary
            type="button"
            onClick={() => onReply({ approved: false, feedback })}
          >
            {t('Reject')}
          </Secondary>
          <StepLine>{t('Nothing is created until you approve.')}</StepLine>
        </Actions>
      </Block>
    );
  }

  return (
    <Block data-test="d2d-questions">
      {questions.map(q => (
        <Question key={q.id}>
          <Ask>{q.question}</Ask>
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
        <Primary type="button" onClick={() => onReply({ answers })}>
          {t('Send answers')}
        </Primary>
        <StepLine>
          {t('Defaults are pre-selected — send as-is to accept them.')}
        </StepLine>
      </Actions>
    </Block>
  );
}
