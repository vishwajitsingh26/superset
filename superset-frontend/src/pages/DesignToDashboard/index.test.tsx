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
import { render, screen } from 'spec/helpers/testing-library';
import {
  Region,
  StageEvent,
} from 'src/features/designToDashboard/useDesignToDashboard';
import DesignToDashboard, {
  regionLabel,
  regionsForPreview,
} from 'src/pages/DesignToDashboard';

// The conversation pane is exercised by its own tests; stubbed here so this
// file is only about the preview pane's region overlay.
jest.mock('src/features/designToDashboard/ChatPanel', () => () => null);

const mockUseDesignToDashboard = jest.fn();
jest.mock('src/features/designToDashboard/useDesignToDashboard', () => ({
  ...jest.requireActual('src/features/designToDashboard/useDesignToDashboard'),
  useDesignToDashboard: () => mockUseDesignToDashboard(),
}));

function region(overrides: Partial<Region>): Region {
  return {
    region_id: 'r01_test',
    title: 'A region',
    bbox: { x: 0.1, y: 0.2, w: 0.3, h: 0.4 },
    ...overrides,
  };
}

function hookState(
  events: StageEvent[],
  overrides: { sessionId?: string | null; imageCount?: number } = {},
) {
  return {
    events,
    state: 'running' as const,
    error: null,
    elapsed: 0,
    thinking: '',
    thinkingStage: '',
    pending: null,
    reply: jest.fn(),
    start: jest.fn(),
    reset: jest.fn(),
    sessionId: null,
    imageCount: 0,
    resume: jest.fn(),
    ...overrides,
  };
}

test('region_label falls back from title to region_id to a generic name', () => {
  expect(regionLabel(region({ title: 'Total Spend' }))).toBe('Total Spend');
  expect(
    regionLabel(region({ title: null, region_id: 'r05_total_spend' })),
  ).toBe('r05_total_spend');
  expect(regionLabel(region({ title: '   ', region_id: undefined }))).toBe(
    'Region',
  );
});

test('regions_for_preview keeps only the first image and only regions with a bbox', () => {
  const kept = regionsForPreview([
    region({ region_id: 'first-image', source_image: 0 }),
    region({ region_id: 'second-image', source_image: 1 }),
    region({ region_id: 'no-image-index' }),
    region({ region_id: 'no-bbox', bbox: undefined }),
  ]);

  expect(kept.map(r => r.region_id)).toEqual(['first-image', 'no-image-index']);
});

test('no design uploaded yet shows the placeholder, not the overlay', () => {
  mockUseDesignToDashboard.mockReturnValue(hookState([]));
  render(<DesignToDashboard />);

  expect(screen.getByText(/your design will appear here/i)).toBeInTheDocument();
  expect(screen.queryByTestId('d2d-region-overlay')).not.toBeInTheDocument();
});

test('a reconnecting tab with no local file still shows the design, from the server', () => {
  // The shape of a page reload: `useDesignToDashboard` has already replayed
  // the session's events (so stage A's regions are known) and reported
  // `imageCount` from the server, but this render never called `onFileChosen`
  // -- there is no browser File object and never will be one again.
  mockUseDesignToDashboard.mockReturnValue(
    hookState([], { sessionId: 'abc-123', imageCount: 1 }),
  );
  render(<DesignToDashboard />);

  const image = screen.getByAltText(/uploaded design/i) as HTMLImageElement;
  expect(image.src).toContain(
    '/api/v1/design_to_dashboard/session/abc-123/asset/0/',
  );
});

test("stage A's regions draw one labelled box each, on top of that same image", () => {
  mockUseDesignToDashboard.mockReturnValue(
    hookState(
      [
        {
          type: 'stage_complete',
          stage: 'A',
          regions: [
            region({ region_id: 'r01_kpi', title: 'Total Spend' }),
            region({ region_id: 'r02_trend', title: null }),
          ],
        },
      ],
      { sessionId: 'abc-123', imageCount: 1 },
    ),
  );
  render(<DesignToDashboard />);

  const overlay = screen.getByTestId('d2d-region-overlay');
  expect(screen.getByText('Total Spend')).toBeInTheDocument();
  expect(screen.getByText('r02_trend')).toBeInTheDocument();
  expect(overlay.children).toHaveLength(2);
});

test('no regions yet (stage A has not finished) means no overlay, just the image', () => {
  mockUseDesignToDashboard.mockReturnValue(
    hookState([], { sessionId: 'abc-123', imageCount: 1 }),
  );
  render(<DesignToDashboard />);

  expect(screen.getByAltText(/uploaded design/i)).toBeInTheDocument();
  expect(screen.queryByTestId('d2d-region-overlay')).not.toBeInTheDocument();
});
