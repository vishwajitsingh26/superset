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
import { styled, useTheme, t } from './adapters/supersetAdapter';
import { CustomSpendingTrendWrapperProps, SpendingTrendView } from './types';
import SegmentedToggle from './components/SegmentedToggle';
import ChildChart from './components/ChildChart';
import { viewToGrain } from './utils/grain';

const VIEWS: SpendingTrendView[] = ['Daily', 'Weekly', 'Monthly'];

// This wrapper's own outer border/radius/shadow is the dashboard's chart
// holder, drawn once for every chart from the design system's card_chrome —
// never redrawn here. The card's plain-text title ("Spending Trend") is
// likewise Superset's own header, not this component's. Only the toggle,
// which the standard header has no slot for, is drawn by this component,
// right-aligned at the very top of the space Superset hands us.
const Root = styled.div`
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
`;

const ToggleRow = styled.div`
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
  padding-bottom: ${({ theme }) => theme.sizeUnit}px;
`;

const Body = styled.div`
  flex: 1;
  min-height: 0;
`;

const EmptyState = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: ${({ theme }) => theme.colorTextTertiary};
`;

export default function CustomSpendingTrendWrapper({
  width,
  height,
  childChartId,
  defaultView,
  isInView,
}: CustomSpendingTrendWrapperProps) {
  const theme = useTheme();
  const [selectedView, setSelectedView] =
    useState<SpendingTrendView>(defaultView);
  const grain = useMemo(() => viewToGrain(selectedView), [selectedView]);
  const toggleRowHeight = theme.sizeUnit * 5;
  const bodyHeight = Math.max(height - toggleRowHeight, 0);

  return (
    <Root data-test="custom-spending-trend-wrapper">
      <ToggleRow>
        <SegmentedToggle
          options={VIEWS}
          value={selectedView}
          onChange={next => setSelectedView(next)}
        />
      </ToggleRow>
      <Body>
        {childChartId === null ? (
          <EmptyState>
            {t('This card is not connected to a chart yet.')}
          </EmptyState>
        ) : (
          <ChildChart
            chartId={childChartId}
            width={width}
            height={bodyHeight}
            isInView={isInView}
            grain={grain}
          />
        )}
      </Body>
    </Root>
  );
}
