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
import { t } from '@apache-superset/core/translation';
import { styled } from '@apache-superset/core/theme';
import ChatPanel from 'src/features/designToDashboard/ChatPanel';
import { useDesignToDashboard } from 'src/features/designToDashboard/useDesignToDashboard';

/**
 * Design-to-Dashboard page shell.
 *
 * The conversation pane and the preview pane are built out in
 * `src/features/designToDashboard/`. This file stays thin: routing,
 * layout frame, and nothing else.
 *
 * Interaction model and build order: `design-to-dashboard/UI_PLAN.md`.
 */

const Layout = styled.div`
  ${({ theme }) => `
    display: flex;
    flex-direction: column;
    height: 100%;
    background-color: ${theme.colorBgLayout};
  `}
`;

const Header = styled.div`
  ${({ theme }) => `
    padding: ${theme.sizeUnit * 4}px ${theme.sizeUnit * 6}px;
    border-bottom: 1px solid ${theme.colorBorder};
    background-color: ${theme.colorBgContainer};
  `}
`;

const Title = styled.h1`
  ${({ theme }) => `
    margin: 0;
    font-size: ${theme.fontSizeXL}px;
    font-weight: ${theme.fontWeightStrong};
    color: ${theme.colorText};
  `}
`;

const Subtitle = styled.p`
  ${({ theme }) => `
    margin: ${theme.sizeUnit}px 0 0;
    color: ${theme.colorTextSecondary};
  `}
`;

const Panes = styled.div`
  ${({ theme }) => `
    display: flex;
    flex: 1;
    min-height: 0;
    gap: ${theme.sizeUnit * 4}px;
    padding: ${theme.sizeUnit * 4}px ${theme.sizeUnit * 6}px;
  `}
`;

const Pane = styled.div`
  ${({ theme }) => `
    flex: 1;
    min-width: 0;
    border: 1px solid ${theme.colorBorder};
    border-radius: ${theme.borderRadius}px;
    background-color: ${theme.colorBgContainer};
    padding: ${theme.sizeUnit * 4}px;
    overflow: auto;
  `}
`;

const Placeholder = styled.div`
  ${({ theme }) => `
    color: ${theme.colorTextTertiary};
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    text-align: center;
  `}
`;

const PreviewImage = styled.img`
  ${({ theme }) => `
    width: 100%;
    height: auto;
    border: 1px solid ${theme.colorBorder};
    border-radius: ${theme.borderRadius}px;
  `}
`;

export default function DesignToDashboard() {
  const {
    events,
    state,
    error,
    elapsed,
    thinking,
    thinkingStage,
    pending,
    reply,
    start,
    reset,
  } = useDesignToDashboard();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [requirement, setRequirement] = useState('');

  // Object URLs leak until revoked. The latest one is mirrored into a ref so
  // unmount cleanup does not have to depend on render state.
  const previewRef = useRef<string | null>(null);

  const setPreview = useCallback((file: File | null) => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    const next = file ? URL.createObjectURL(file) : null;
    previewRef.current = next;
    setPreviewUrl(next);
  }, []);

  useEffect(
    () => () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    },
    [],
  );

  // The preview shows the first image; stage A reads all of them.
  const onFileChosen = useCallback(
    (files: File[]) => setPreview(files[0] ?? null),
    [setPreview],
  );

  const onReset = useCallback(() => {
    reset();
    setPreview(null);
    setRequirement('');
  }, [reset, setPreview]);

  return (
    <Layout>
      <Header>
        <Title>{t('Design to Dashboard')}</Title>
        <Subtitle>
          {t(
            'Upload a design and describe what you need. Charts are reused ' +
              'where they exist and configured where they do not.',
          )}
        </Subtitle>
      </Header>
      <Panes>
        <Pane data-test="d2d-conversation-pane">
          <ChatPanel
            events={events}
            state={state}
            elapsed={elapsed}
            thinking={thinking}
            thinkingStage={thinkingStage}
            pending={pending}
            onReply={reply}
            error={error}
            requirement={requirement}
            previewUrl={previewUrl}
            onRequirementChange={setRequirement}
            onStart={start}
            onReset={onReset}
            onFileChosen={onFileChosen}
          />
        </Pane>
        <Pane data-test="d2d-preview-pane">
          {previewUrl ? (
            <PreviewImage src={previewUrl} alt={t('Uploaded design')} />
          ) : (
            <Placeholder>
              {t('Your design will appear here once you choose a file.')}
            </Placeholder>
          )}
        </Pane>
      </Panes>
    </Layout>
  );
}
