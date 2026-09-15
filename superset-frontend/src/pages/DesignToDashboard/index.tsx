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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { styled } from '@apache-superset/core/theme';
import ChatPanel from 'src/features/designToDashboard/ChatPanel';
import {
  assetUrl,
  Region,
  useDesignToDashboard,
} from 'src/features/designToDashboard/useDesignToDashboard';

/**
 * Design-to-Dashboard page shell.
 *
 * The conversation pane and the preview pane are built out in
 * `src/features/designToDashboard/`. This file stays thin: routing,
 * layout frame, and nothing else.
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
    display: block;
    width: 100%;
    height: auto;
    border: 1px solid ${theme.colorBorder};
    border-radius: ${theme.borderRadius}px;
  `}
`;

/**
 * Positions the region overlay against the rendered image rather than its
 * natural size -- `PreviewImage` is scaled to the pane's width, and the
 * boxes are drawn in the same percentage units `bbox` already uses, so they
 * track that scaling for free.
 */
const PreviewFrame = styled.div`
  position: relative;
  display: inline-block;
  width: 100%;
`;

const RegionOverlay = styled.div`
  position: absolute;
  inset: 0;
  overflow: visible;
  pointer-events: none;
`;

const RegionBox = styled.div`
  ${({ theme }) => `
    position: absolute;
    box-sizing: border-box;
    border: 2px solid ${theme.colorError};
  `}
`;

const RegionLabel = styled.span`
  ${({ theme }) => `
    position: absolute;
    top: 0;
    left: 0;
    transform: translateY(-100%);
    max-width: 100%;
    padding: 0 ${theme.sizeUnit}px;
    background-color: ${theme.colorError};
    color: ${theme.colorWhite};
    font-size: ${theme.fontSizeSM}px;
    line-height: ${theme.sizeUnit * 4}px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  `}
`;

/** What a region shows in its tag: the title a human would recognise it by,
 * falling back to its id -- filters and icon-only controls are often read
 * with no title at all. */
export function regionLabel(region: Region): string {
  return region.title?.trim() || region.region_id || t('Region');
}

/** A region known to have a `bbox` -- the box's position/size need never be
 * re-checked once a region has passed through `regionsForPreview`. */
export type PositionedRegion = Region & { bbox: NonNullable<Region['bbox']> };

/** Stage A can read more than one uploaded image; the preview only ever
 * shows the first, so only its regions belong on top of it. */
export function regionsForPreview(regions: Region[]): PositionedRegion[] {
  return regions.filter(
    (region): region is PositionedRegion =>
      (region.source_image ?? 0) === 0 && Boolean(region.bbox),
  );
}

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
    sessionId,
    imageCount,
    start,
    reset,
  } = useDesignToDashboard();
  // The tab that just chose a file has it as a blob URL, instantly and with
  // no round trip. A tab that reconnects to an existing session -- a reload,
  // or the link shared -- never had that `File` object, only the id in the
  // address bar: `imageCount` (from the session itself) says whether the
  // server now has something to draw, and `assetUrl` is where to draw it
  // from. Either source ends up in the same place both panes read from.
  const [localPreviewUrl, setLocalPreviewUrl] = useState<string | null>(null);
  const previewUrl =
    localPreviewUrl ??
    (sessionId && imageCount > 0 ? assetUrl(sessionId) : null);
  const [requirement, setRequirement] = useState('');

  // Stage A's own event, not the running state -- its regions stay on
  // screen through every later stage rather than disappearing once A is no
  // longer the one in flight.
  const regions = useMemo(() => {
    const read = [...events]
      .reverse()
      .find(event => event.type === 'stage_complete' && event.stage === 'A');
    return regionsForPreview(read?.regions ?? []);
  }, [events]);

  // Object URLs leak until revoked. The latest one is mirrored into a ref so
  // unmount cleanup does not have to depend on render state.
  const previewRef = useRef<string | null>(null);

  const setPreview = useCallback((file: File | null) => {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    const next = file ? URL.createObjectURL(file) : null;
    previewRef.current = next;
    setLocalPreviewUrl(next);
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
            <PreviewFrame>
              <PreviewImage src={previewUrl} alt={t('Uploaded design')} />
              {regions.length > 0 && (
                <RegionOverlay data-test="d2d-region-overlay">
                  {regions.map(region => {
                    const { x, y, w, h } = region.bbox;
                    return (
                      <RegionBox
                        key={region.region_id ?? `${x}-${y}-${w}-${h}`}
                        style={{
                          left: `${x * 100}%`,
                          top: `${y * 100}%`,
                          width: `${w * 100}%`,
                          height: `${h * 100}%`,
                        }}
                      >
                        <RegionLabel>{regionLabel(region)}</RegionLabel>
                      </RegionBox>
                    );
                  })}
                </RegionOverlay>
              )}
            </PreviewFrame>
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
