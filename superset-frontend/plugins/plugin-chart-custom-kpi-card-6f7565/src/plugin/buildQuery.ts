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
import {
  buildQueryContext,
  QueryFormColumn,
} from '../adapters/supersetAdapter';
import { presentMetrics } from '../adapters/optionalMetrics';
import { CustomKpiCardFormData } from '../types';
import { DEFAULT_TREND_PERIODS, MIN_TREND_PERIODS } from '../utils/constants';
import { widenedSeriesFormData } from '../utils/timeWindow';

// Query 1 (headline): the metric aggregated over the dashboard's own date
// range -- this is the big number.
// Query 2 (series): the same metric grouped by the temporal column, over a
// window widened from the dashboard's range, anchored to its end. It feeds
// both the sparkline and the period-over-period delta; the headline query
// alone may be a single row and cannot supply either.
export default function buildQuery(formData: CustomKpiCardFormData) {
  const metrics = presentMetrics([formData.metric]);

  const headlineContext = buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      groupby: [],
      metrics,
      row_limit: 1,
    },
  ]);

  const timeColumn = formData.granularity_sqla as QueryFormColumn | undefined;
  if (!timeColumn || metrics.length === 0) {
    return headlineContext;
  }

  const trendPeriods = Math.max(
    MIN_TREND_PERIODS,
    Number(formData.trendPeriods) || DEFAULT_TREND_PERIODS,
  );
  const seriesFormData = widenedSeriesFormData(formData, trendPeriods);

  const seriesContext = buildQueryContext(seriesFormData, baseQueryObject => [
    {
      ...baseQueryObject,
      groupby: [timeColumn],
      metrics,
      row_limit: trendPeriods,
    },
  ]);

  return {
    ...headlineContext,
    queries: [...headlineContext.queries, ...seriesContext.queries],
  };
}
