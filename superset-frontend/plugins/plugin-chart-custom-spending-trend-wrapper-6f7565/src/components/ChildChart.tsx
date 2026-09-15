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
import { useMemo } from 'react';
import { useSelector } from 'react-redux';
import ChartContainer from 'src/components/Chart/ChartContainer';
import { PLACEHOLDER_DATASOURCE } from 'src/dashboard/constants';
import type { ChartState, ChartStatus, Datasource } from 'src/explore/types';
import {
  styled,
  t,
  Empty,
  ExtraFormData,
  JsonObject,
  QueryFormData,
  TimeGranularity,
} from '../adapters/supersetAdapter';
import { mergeExtraFormData } from '../utils/extraFormData';
import {
  useBootstrapEmbeddedChart,
  useAbortChartDataOnUnmount,
  useTriggerQueryOnMount,
  useTriggerQueryOnChange,
} from '../utils/chartHostHooks';

const NATIVE_FILTER_PREFIX = 'NATIVE_FILTER-';

interface ChildChartProps {
  chartId: number;
  width: number;
  height: number;
  isInView: boolean;
  grain: TimeGranularity;
}

interface RootState {
  charts: Record<
    number,
    {
      id: number;
      chartStatus?: ChartStatus;
      chartAlert?: string | null;
      queriesResponse?: ChartState['queriesResponse'];
      triggerQuery?: boolean;
      annotationData?: JsonObject;
      latestQueryFormData?: QueryFormData;
      queryController?: AbortController | null;
    }
  >;
  sliceEntities?: {
    slices?: Record<
      number,
      { slice_id: number; slice_name: string; viz_type: string }
    >;
  };
  datasources?: Record<string, Datasource>;
  dataMask?: Record<string, { extraFormData?: ExtraFormData } | undefined>;
  dashboardInfo?: {
    id?: number;
    common?: { conf?: { SUPERSET_WEBSERVER_TIMEOUT?: number } };
    crossFiltersEnabled?: boolean;
  };
  dashboardState?: { datasetsStatus?: 'loading' | 'error' | 'complete' };
}

const Root = styled.div`
  position: relative;
  width: 100%;
  height: 100%;
`;

const Centered = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const noop = () => {};

export default function ChildChart({
  chartId,
  width,
  height,
  isInView,
  grain,
}: ChildChartProps) {
  const chart = useSelector((s: RootState) => s.charts?.[chartId]);
  const slice = useSelector(
    (s: RootState) => s.sliceEntities?.slices?.[chartId],
  );

  useBootstrapEmbeddedChart(chartId, !!chart, !!slice);
  useAbortChartDataOnUnmount(chartId);

  const datasource = useSelector((s: RootState) => {
    const key = chart?.latestQueryFormData?.datasource;
    if (typeof key === 'string' && s.datasources?.[key])
      return s.datasources[key];
    return PLACEHOLDER_DATASOURCE;
  });

  const nativeFiltersJson = useSelector((s: RootState) => {
    const dm = s.dataMask;
    if (!dm) return '';
    let merged: ExtraFormData = {};
    Object.entries(dm).forEach(([key, entry]) => {
      if (key === String(chartId)) return;
      const hasData =
        entry?.extraFormData && Object.keys(entry.extraFormData).length > 0;
      if (!hasData) return;
      const isNative = key.startsWith(NATIVE_FILTER_PREFIX);
      const isCross = /^\d+$/.test(key);
      if (isNative || isCross)
        merged = mergeExtraFormData(merged, entry!.extraFormData!);
    });
    return Object.keys(merged).length > 0 ? JSON.stringify(merged) : '';
  });
  const nativeFiltersExtraFormData: ExtraFormData | undefined = useMemo(
    () => (nativeFiltersJson ? JSON.parse(nativeFiltersJson) : undefined),
    [nativeFiltersJson],
  );

  const timeout = useSelector(
    (s: RootState) =>
      s.dashboardInfo?.common?.conf?.SUPERSET_WEBSERVER_TIMEOUT ?? 60,
  );
  const dashboardId = useSelector((s: RootState) => s.dashboardInfo?.id);
  const emitCrossFilters = useSelector(
    (s: RootState) => !!s.dashboardInfo?.crossFiltersEnabled,
  );
  const datasetsStatus = useSelector(
    (s: RootState) => s.dashboardState?.datasetsStatus,
  );

  const ready = !!chart && !!slice;
  useTriggerQueryOnMount(chartId, ready);
  useTriggerQueryOnChange(chartId, ready, `${grain}|${nativeFiltersJson}`);

  const formData = useMemo(() => {
    if (!chart || !slice) return null;
    const baseExtra = (chart.latestQueryFormData?.extra_form_data ??
      {}) as ExtraFormData;
    const mergedExtra = nativeFiltersExtraFormData
      ? mergeExtraFormData(baseExtra, nativeFiltersExtraFormData)
      : baseExtra;
    return {
      ...chart.latestQueryFormData,
      // `latestQueryFormData.datasource` is `string | undefined` on the shared
      // type, but the bootstrap fetch above always sets it once the chart is
      // hydrated; ChartContainer's own formData prop requires a definite
      // string, so pin it explicitly rather than letting the spread's
      // optional field carry through.
      datasource: chart.latestQueryFormData?.datasource ?? '',
      slice_id: slice.slice_id,
      viz_type: slice.viz_type,
      dashboardId,
      // The wrapper's own Daily/Weekly/Monthly toggle overrides the hosted
      // chart's own time grain — this is the whole point of hosting it here.
      time_grain_sqla: grain,
      extra_form_data: mergedExtra,
    };
  }, [chart, slice, dashboardId, grain, nativeFiltersExtraFormData]);

  if (!ready || !formData) {
    return <Root data-test={`spending-trend-child-${chartId}`} />;
  }

  if (!chart.id) {
    return (
      <Root data-test={`spending-trend-child-${chartId}`}>
        <Centered>
          <Empty description={t('Chart not available')} />
        </Centered>
      </Root>
    );
  }

  return (
    <Root data-test={`spending-trend-child-${chartId}`}>
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
        queriesResponse={chart.queriesResponse}
        timeout={timeout}
        triggerQuery={chart.triggerQuery}
        vizType={slice.viz_type}
        setControlValue={noop}
        datasetsStatus={datasetsStatus}
        isInView={isInView}
        emitCrossFilters={emitCrossFilters}
      />
    </Root>
  );
}
