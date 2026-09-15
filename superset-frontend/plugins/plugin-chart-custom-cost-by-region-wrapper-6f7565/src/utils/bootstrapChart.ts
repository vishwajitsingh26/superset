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
// Internal Superset app modules, not `@superset-ui/*` -- outside this
// package's adapter barrel, and the only way to reach the same redux slices
// a real dashboard tile is bootstrapped into.
import { addChart } from 'src/components/Chart/chartAction';
import { chart as initChart } from 'src/components/Chart/chartReducer';
import { fetchDatasourceMetadata } from 'src/dashboard/actions/datasources';
import { SupersetClient, JsonObject } from '../adapters/supersetAdapter';
import { RootState } from '../components/rootState';

// Fetches a hosted chart's own saved params exactly once, the first time
// this wrapper renders it and redux has never heard of it -- because unlike
// a grid tile, nothing else primes this chart into the store first.
export function useBootstrapChart(chartId: number | undefined): void {
  const dispatch = useDispatch();
  const hasChart = useSelector(
    (s: RootState) => !!(chartId && s.charts?.[chartId]),
  );
  const hasSlice = useSelector(
    (s: RootState) => !!(chartId && s.sliceEntities?.slices?.[chartId]),
  );
  const bootstrapped = useRef(false);

  useEffect(() => {
    if (!chartId || (hasChart && hasSlice) || bootstrapped.current)
      return undefined;
    bootstrapped.current = true;
    const controller = new AbortController();

    (async () => {
      try {
        const response = await SupersetClient.get({
          endpoint: `/api/v1/chart/${chartId}`,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        const result = (response.json as JsonObject).result as
          | JsonObject
          | undefined;
        if (!result) return;

        const params =
          typeof result.params === 'string'
            ? JSON.parse(result.params)
            : result.params || {};
        const datasourceKey = `${result.datasource_id}__${result.datasource_type}`;
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
                  slice_name: result.slice_name || '',
                  slice_url: result.url || '',
                  form_data: formData,
                  viz_type: result.viz_type || params.viz_type || '',
                  datasource: datasourceKey,
                  description: result.description || '',
                  description_markeddown: result.description_markeddown || '',
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
        bootstrapped.current = false;
      }
    })();

    return (): void => controller.abort();
  }, [chartId, hasChart, hasSlice, dispatch]);
}
