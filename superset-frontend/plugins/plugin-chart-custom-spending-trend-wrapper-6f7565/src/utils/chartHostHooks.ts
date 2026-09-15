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
// Mirrors the mechanism the container archetype's reference plugin uses to
// pull a saved chart's slice + chart entities into the dashboard's own redux
// store, so `ChartContainer` can render it exactly as the grid would.
import { useEffect, useRef } from 'react';
import { useDispatch, useStore } from 'react-redux';
import { addChart, triggerQuery } from 'src/components/Chart/chartAction';
import { chart as initChart } from 'src/components/Chart/chartReducer';
import { fetchDatasourceMetadata } from 'src/dashboard/actions/datasources';
import { SupersetClient } from '../adapters/supersetAdapter';

export function useBootstrapEmbeddedChart(
  chartId: number,
  hasChart: boolean,
  hasSlice: boolean,
): void {
  const dispatch = useDispatch();
  const bootstrappedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (hasChart && hasSlice) return undefined;
    if (bootstrappedRef.current.has(chartId)) return undefined;
    bootstrappedRef.current.add(chartId);
    const controller = new AbortController();

    (async () => {
      try {
        const response = await SupersetClient.get({
          endpoint: `/api/v1/chart/${chartId}`,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        const chartData = (response.json as Record<string, unknown>).result as
          | Record<string, unknown>
          | undefined;
        if (!chartData) return;
        const params =
          typeof chartData.params === 'string'
            ? JSON.parse(chartData.params)
            : chartData.params || {};
        const datasourceId = chartData.datasource_id as number;
        const datasourceType = chartData.datasource_type as string;
        const datasourceKey = `${datasourceId}__${datasourceType}`;
        const formData = {
          ...params,
          slice_id: chartId,
          datasource: datasourceKey,
        };

        if (!hasChart) {
          dispatch(
            addChart(
              { ...initChart, id: chartId, latestQueryFormData: formData },
              chartId,
            ),
          );
        }
        if (!hasSlice) {
          dispatch({
            type: 'ADD_SLICES',
            payload: {
              slices: {
                [chartId]: {
                  slice_id: chartId,
                  slice_name: (chartData.slice_name as string) || '',
                  slice_url: (chartData.url as string) || '',
                  form_data: formData,
                  viz_type:
                    (chartData.viz_type as string) || params.viz_type || '',
                  datasource: datasourceKey,
                  description: (chartData.description as string) || '',
                  description_markeddown:
                    (chartData.description_markeddown as string) || '',
                },
              },
            },
          });
        }
        if (datasourceKey) {
          dispatch(fetchDatasourceMetadata(datasourceKey) as unknown as never);
        }
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === 'AbortError')
          return;
        bootstrappedRef.current.delete(chartId);
      }
    })();

    return (): void => {
      controller.abort();
    };
  }, [chartId, hasChart, hasSlice, dispatch]);
}

export function useAbortChartDataOnUnmount(chartId: number): void {
  const { getState } = useStore();
  useEffect(
    () => () => {
      const state = getState() as {
        charts?: Record<number, { queryController?: AbortController | null }>;
      };
      const controller = state.charts?.[chartId]?.queryController ?? null;
      controller?.abort();
    },
    [chartId, getState],
  );
}

export function useTriggerQueryOnMount(chartId: number, ready: boolean): void {
  const dispatch = useDispatch();
  const firedRef = useRef(false);
  useEffect(() => {
    if (ready && !firedRef.current) {
      firedRef.current = true;
      dispatch(triggerQuery(true, chartId));
    }
  }, [ready, chartId, dispatch]);
}

export function useTriggerQueryOnChange(
  chartId: number,
  ready: boolean,
  signature: string,
): void {
  const dispatch = useDispatch();
  const prevRef = useRef(signature);
  const mountedRef = useRef(false);
  useEffect(() => {
    if (!ready) return;
    if (prevRef.current !== signature) {
      prevRef.current = signature;
      if (mountedRef.current) dispatch(triggerQuery(true, chartId));
    }
    mountedRef.current = true;
  }, [signature, ready, chartId, dispatch]);
}
