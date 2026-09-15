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
// @ts-ignore -- React is needed at runtime for JSX
import React, { useMemo } from 'react';
import { styled } from './adapters/supersetAdapter';
import ChildChartSlot from './components/ChildChartSlot';
import { CustomCostByRegionWrapperProps } from './types';

// The crop shows the map and the list splitting the card exactly in half,
// with no divider drawn beyond the whitespace between them.
const GAP_PX = 24;

const Row = styled.div`
  display: flex;
  flex-direction: row;
  align-items: stretch;
  width: 100%;
  height: 100%;
  gap: ${GAP_PX}px;
`;

const Column = styled.div<{ $width: number }>`
  flex: 0 0 ${({ $width }) => $width}px;
  min-width: 0;
  height: 100%;
`;

// Never draws a card of its own: Superset's own chart holder already draws
// the one border this card shows, and the two slots below sit bare inside
// it, exactly as the design draws them -- no divider, only whitespace.
export default function CustomCostByRegionWrapper({
  width,
  height,
  mapChartId,
  listChartId,
}: CustomCostByRegionWrapperProps) {
  const { mapWidth, listWidth } = useMemo(() => {
    const available = Math.max(0, width - GAP_PX);
    const map = Math.floor(available / 2);
    return { mapWidth: map, listWidth: available - map };
  }, [width]);

  return (
    <Row data-test="custom-cost-by-region-wrapper">
      <Column $width={mapWidth}>
        <ChildChartSlot chartId={mapChartId} width={mapWidth} height={height} />
      </Column>
      <Column $width={listWidth}>
        <ChildChartSlot
          chartId={listChartId}
          width={listWidth}
          height={height}
        />
      </Column>
    </Row>
  );
}
