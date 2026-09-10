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
  QueryFormMetric,
  QueryFormOrderBy,
  buildQueryContext,
  ensureIsArray,
  getColumnLabel,
} from '../adapters/supersetAdapter';
import { DEFAULT_TREND_PERIODS } from '../constants';
import { SpendCardFormData } from '../types';

export default function buildQuery(formData: SpendCardFormData) {
  const { metric, shareTotalMetric, driverDimension, x_axis: xAxis } = formData;
  const periods = Number(formData.trendPeriods) || DEFAULT_TREND_PERIODS;
  const valueMetrics = ensureIsArray<QueryFormMetric>(metric);
  const trendMetrics = valueMetrics.concat(
    ensureIsArray<QueryFormMetric>(shareTotalMetric),
  );
  const xLabel = xAxis ? getColumnLabel(xAxis) : '';

  return buildQueryContext(formData, baseQueryObject => {
    // Newest periods first so row_limit keeps the latest window; the series is
    // reversed once in transformProps.
    const trendQuery = {
      ...baseQueryObject,
      metrics: trendMetrics,
      columns: xAxis ? [xAxis] : [],
      orderby: xLabel ? ([[xLabel, false]] as QueryFormOrderBy[]) : [],
      row_limit: periods,
    };

    if (!driverDimension) {
      return [trendQuery];
    }

    // Different dimension and grain from the trend, so it cannot be derived
    // from the rows above.
    const driverQuery = {
      ...baseQueryObject,
      metrics: valueMetrics,
      columns: [driverDimension],
      orderby: metric ? ([[metric, false]] as QueryFormOrderBy[]) : [],
      row_limit: 1,
    };

    return [trendQuery, driverQuery];
  });
}
