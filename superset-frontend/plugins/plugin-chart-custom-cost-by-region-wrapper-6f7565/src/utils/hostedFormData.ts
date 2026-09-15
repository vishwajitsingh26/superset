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
import { useEffect, useMemo, useRef } from 'react';
import { useDispatch, useSelector, useStore } from 'react-redux';
import { triggerQuery } from 'src/components/Chart/chartAction';
import { PLACEHOLDER_DATASOURCE } from 'src/dashboard/constants';
import type { Datasource } from 'src/explore/types';
import { JsonObject, QueryFormData } from '../adapters/supersetAdapter';
import { mergeExtraFormData, ExtraFormData } from './extraFormData';
import { RootState, ChartEntry, SliceEntry } from '../components/rootState';

const NATIVE_FILTER_PREFIX = 'NATIVE_FILTER-';

export interface HostedFormData {
  ready: boolean;
  chart?: ChartEntry;
  slice?: SliceEntry;
  formData: QueryFormData | null;
  datasource: Datasource;
  ownState?: JsonObject;
  timeout: number;
  emitCrossFilters: boolean;
  datasetsStatus?: 'loading' | 'error' | 'complete';
  dashboardId?: number;
}

// Assembles the form data a hosted chart needs to render as if it were a
// grid tile: its own saved params, plus every native/cross filter on the
// dashboard except the one keyed to this chart's own id, so a chart hosted
// inside this wrapper still moves with the dashboard's own filters.
export function useHostedFormData(chartId: number | undefined): HostedFormData {
  const dispatch = useDispatch();
  const { getState } = useStore();

  const chart = useSelector((s: RootState) =>
    chartId ? s.charts?.[chartId] : undefined,
  );
  const slice = useSelector((s: RootState) =>
    chartId ? s.sliceEntities?.slices?.[chartId] : undefined,
  );
  const ready = !!chart && !!slice;

  useEffect(
    () => () => {
      if (!chartId) return;
      (getState() as RootState).charts?.[chartId]?.queryController?.abort();
    },
    [chartId, getState],
  );

  const datasource = useSelector((s: RootState) => {
    const key = chart?.latestQueryFormData?.datasource;
    return typeof key === 'string' && s.datasources?.[key]
      ? s.datasources[key]
      : PLACEHOLDER_DATASOURCE;
  });

  const dataMaskEntry = useSelector((s: RootState) =>
    chartId ? s.dataMask?.[chartId] : undefined,
  );

  const nativeFiltersJson = useSelector((s: RootState) => {
    const dm = s.dataMask;
    if (!dm) return '';
    let merged: ExtraFormData = {};
    Object.entries(dm).forEach(([key, entry]) => {
      if (key === String(chartId)) return;
      const hasExtra =
        entry?.extraFormData && Object.keys(entry.extraFormData).length > 0;
      if (!hasExtra) return;
      if (key.startsWith(NATIVE_FILTER_PREFIX) || /^\d+$/.test(key)) {
        merged = mergeExtraFormData(merged, entry!.extraFormData!);
      }
    });
    return Object.keys(merged).length > 0 ? JSON.stringify(merged) : '';
  });

  const nativeExtra = useMemo<ExtraFormData | undefined>(
    () => (nativeFiltersJson ? JSON.parse(nativeFiltersJson) : undefined),
    [nativeFiltersJson],
  );

  const timeout = useSelector(
    (s: RootState) =>
      s.dashboardInfo?.common?.conf?.SUPERSET_WEBSERVER_TIMEOUT ?? 60,
  );
  const emitCrossFilters = useSelector(
    (s: RootState) => !!s.dashboardInfo?.crossFiltersEnabled,
  );
  const datasetsStatus = useSelector(
    (s: RootState) => s.dashboardState?.datasetsStatus,
  );
  const dashboardId = useSelector((s: RootState) => s.dashboardInfo?.id);

  const initialFired = useRef(false);
  useEffect(() => {
    if (!ready || !chartId || initialFired.current) return;
    initialFired.current = true;
    if (chart!.triggerQuery) return;
    const live =
      chart!.chartStatus === 'loading' &&
      chart!.queryController &&
      !chart!.queryController.signal.aborted;
    if (!live) dispatch(triggerQuery(true, chartId));
  }, [ready, chartId, chart, dispatch]);

  const prevNative = useRef(nativeFiltersJson);
  const nativeMounted = useRef(false);
  useEffect(() => {
    if (!ready || !chartId) return;
    if (prevNative.current !== nativeFiltersJson) {
      prevNative.current = nativeFiltersJson;
      if (nativeMounted.current) dispatch(triggerQuery(true, chartId));
    }
    nativeMounted.current = true;
  }, [nativeFiltersJson, ready, chartId, dispatch]);

  const formData = useMemo<QueryFormData | null>(() => {
    if (!chart || !slice) return null;
    const base = (chart.latestQueryFormData?.extra_form_data ??
      {}) as ExtraFormData;
    const merged = nativeExtra ? mergeExtraFormData(base, nativeExtra) : base;
    return {
      ...chart.latestQueryFormData,
      slice_id: slice.slice_id,
      viz_type: slice.viz_type,
      dashboardId,
      extra_form_data: merged,
    } as QueryFormData;
  }, [chart, slice, dashboardId, nativeExtra]);

  return {
    ready,
    chart,
    slice,
    formData,
    datasource,
    ownState: dataMaskEntry?.ownState,
    timeout,
    emitCrossFilters,
    datasetsStatus,
    dashboardId,
  };
}
