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
import { useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { addChart } from 'src/components/Chart/chartAction';
import { chart as initChart } from 'src/components/Chart/chartReducer';
import { fetchDatasourceMetadata } from 'src/dashboard/actions/datasources';
import { SupersetClient } from '../adapters/supersetAdapter';
import { EmbeddedRootState } from '../types';

interface ChartApiResult {
  params?: string | Record<string, unknown>;
  datasource_id?: number;
  datasource_type?: string;
  slice_name?: string;
  viz_type?: string;
  url?: string;
  description?: string;
}

// Loads a saved chart into the dashboard store so it can render inside the
// panel even when it is not a grid child of the dashboard.
export default function useEmbeddedChart(chartId: number): boolean {
  const dispatch = useDispatch<(action: unknown) => void>();
  const hasChart = useSelector((s: EmbeddedRootState) =>
    Boolean(s.charts?.[chartId]),
  );
  const hasSlice = useSelector((s: EmbeddedRootState) =>
    Boolean(s.sliceEntities?.slices?.[chartId]),
  );
  const requested = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!chartId || (hasChart && hasSlice)) return undefined;
    if (requested.current.has(chartId)) return undefined;
    requested.current.add(chartId);

    const controller = new AbortController();
    SupersetClient.get({
      endpoint: `/api/v1/chart/${chartId}`,
      signal: controller.signal,
    })
      .then(response => {
        const { result } = response.json as { result?: ChartApiResult };
        if (!result || controller.signal.aborted) return;
        const params =
          typeof result.params === 'string'
            ? (JSON.parse(result.params) as Record<string, unknown>)
            : (result.params ?? {});
        const datasource = `${result.datasource_id}__${result.datasource_type}`;
        const formData = { ...params, slice_id: chartId, datasource };

        if (!hasChart) {
          dispatch(
            addChart({ ...initChart, id: chartId, latestQueryFormData: formData }, chartId),
          );
        }
        if (!hasSlice) {
          dispatch({
            type: 'ADD_SLICES',
            payload: {
              slices: {
                [chartId]: {
                  slice_id: chartId,
                  slice_name: result.slice_name ?? '',
                  slice_url: result.url ?? '',
                  latestQueryFormData: formData,
                  viz_type: result.viz_type ?? '',
                  datasource,
                  description: result.description ?? '',
                },
              },
            },
          });
        }
        if (result.datasource_id !== undefined) {
          dispatch(fetchDatasourceMetadata(datasource));
        }
      })
      .catch(() => {
        requested.current.delete(chartId);
      });

    return () => controller.abort();
  }, [chartId, hasChart, hasSlice, dispatch]);

  return hasChart && hasSlice;
}
