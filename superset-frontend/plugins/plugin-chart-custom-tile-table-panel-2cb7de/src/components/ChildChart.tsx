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
import { FC, memo, useEffect, useMemo, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import ChartContainerBase from 'src/components/Chart/ChartContainer';
import { triggerQuery } from 'src/components/Chart/chartAction';
import { PLACEHOLDER_DATASOURCE } from 'src/dashboard/constants';
import { t } from '../adapters/supersetAdapter';
import { ChildChartProps, EmbeddedRootState } from '../types';
import useEmbeddedChart from '../utils/useEmbeddedChart';
import { ChildFallback } from '../PanelStyles';

const ChartContainer = ChartContainerBase as unknown as FC<
  Record<string, unknown>
>;
const noop = () => {};

const ChildChart: FC<ChildChartProps> = ({
  chartId,
  dashboardId,
  width,
  height,
}) => {
  const ready = useEmbeddedChart(chartId);
  const dispatch = useDispatch<(action: unknown) => void>();
  const chart = useSelector((s: EmbeddedRootState) => s.charts?.[chartId]);
  const slice = useSelector(
    (s: EmbeddedRootState) => s.sliceEntities?.slices?.[chartId],
  );
  const datasource = useSelector((s: EmbeddedRootState) => {
    const key = chart?.form_data?.datasource;
    if (typeof key === 'string' && s.datasources?.[key]) {
      return s.datasources[key];
    }
    return PLACEHOLDER_DATASOURCE;
  });
  const ownState = useSelector(
    (s: EmbeddedRootState) => s.dataMask?.[String(chartId)]?.ownState,
  );
  const timeout = useSelector(
    (s: EmbeddedRootState) =>
      s.dashboardInfo?.common?.conf?.SUPERSET_WEBSERVER_TIMEOUT ?? 60,
  );
  const emitCrossFilters = useSelector((s: EmbeddedRootState) =>
    Boolean(s.dashboardInfo?.crossFiltersEnabled),
  );
  const datasetsStatus = useSelector(
    (s: EmbeddedRootState) => s.dashboardState?.datasetsStatus,
  );

  const fired = useRef(false);
  useEffect(() => {
    if (!ready || fired.current) return;
    fired.current = true;
    if (chart?.triggerQuery) return;
    const live =
      chart?.chartStatus === 'loading' &&
      chart?.queryController &&
      !chart.queryController.signal.aborted;
    if (live) return;
    dispatch(triggerQuery(true, chartId));
  }, [ready, chartId, dispatch, chart]);

  const formData = useMemo(() => {
    if (!chart || !slice) return null;
    return {
      ...(chart.form_data ?? {}),
      slice_id: slice.slice_id,
      viz_type: slice.viz_type,
      dashboardId,
    };
  }, [chart, slice, dashboardId]);

  if (chart?.chartAlert) {
    return <ChildFallback $height={height}>{chart.chartAlert}</ChildFallback>;
  }

  if (!ready || !slice || !formData) {
    return <ChildFallback $height={height}>{t('Loading...')}</ChildFallback>;
  }

  return (
    <ChartContainer
      width={width}
      height={height}
      chartId={chartId}
      dashboardId={dashboardId}
      vizType={slice.viz_type}
      formData={formData}
      datasource={datasource}
      ownState={ownState}
      annotationData={chart?.annotationData}
      chartStatus={chart?.chartStatus}
      queriesResponse={chart?.queriesResponse}
      triggerQuery={chart?.triggerQuery}
      timeout={timeout}
      datasetsStatus={datasetsStatus}
      emitCrossFilters={emitCrossFilters}
      isInView
      initialValues={{}}
      addFilter={noop}
      onFilterMenuOpen={noop}
      onFilterMenuClose={noop}
      setControlValue={noop}
    />
  );
};

export default memo(ChildChart);
