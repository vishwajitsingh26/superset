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
import React from 'react';
import ChartContainer from 'src/components/Chart/ChartContainer';
import { Empty, styled, t, useTheme } from '../adapters/supersetAdapter';
import { useBootstrapChart } from '../utils/bootstrapChart';
import { useHostedFormData } from '../utils/hostedFormData';

const noop = (): void => {};

const Slot = styled.div`
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  overflow: hidden;

  .chart-container,
  .slice_container {
    height: 100% !important;
  }
`;

const Centered = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
`;

interface ChildChartSlotProps {
  chartId?: number;
  width: number;
  height: number;
}

// Hosts exactly one already-saved chart by id, filling the slot it is given.
// This never re-implements what the child draws -- it only bootstraps the
// child into redux, keeps it in sync with the dashboard's own filters, and
// renders Superset's own ChartContainer around it.
export default function ChildChartSlot({
  chartId,
  width,
  height,
}: ChildChartSlotProps) {
  const theme = useTheme();
  useBootstrapChart(chartId);
  const {
    ready,
    chart,
    slice,
    formData,
    datasource,
    ownState,
    timeout,
    emitCrossFilters,
    datasetsStatus,
    dashboardId,
  } = useHostedFormData(chartId);

  if (!chartId) {
    return (
      <Slot>
        <Centered>
          <Empty description={t('No chart configured')} />
        </Centered>
      </Slot>
    );
  }

  if (!ready || !formData || !chart || !slice) {
    return (
      <Slot>
        <Centered style={{ color: theme.colorTextTertiary }}>
          {t('Loading…')}
        </Centered>
      </Slot>
    );
  }

  return (
    <Slot data-test={`cost-by-region-slot-${chartId}`}>
      <ChartContainer
        width={width}
        height={height}
        addFilter={noop}
        onFilterMenuOpen={noop}
        onFilterMenuClose={noop}
        annotationData={chart.annotationData}
        chartAlert={chart.chartAlert ?? undefined}
        chartId={chartId}
        chartStatus={chart.chartStatus}
        datasource={datasource}
        dashboardId={dashboardId}
        initialValues={{}}
        formData={formData}
        ownState={ownState}
        queriesResponse={chart.queriesResponse}
        timeout={timeout}
        triggerQuery={chart.triggerQuery}
        vizType={slice.viz_type}
        setControlValue={noop}
        datasetsStatus={datasetsStatus}
        isInView
        emitCrossFilters={emitCrossFilters}
      />
    </Slot>
  );
}
