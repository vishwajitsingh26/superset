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
  QueryFormColumn,
  QueryFormMetric,
  QueryFormOrderBy,
  buildQueryContext,
} from '../adapters/supersetAdapter';
import { ProviderSpendCardFormData } from '../types';

const DEFAULT_PERIODS = 6;

// One query carries the trend plus every value derived from it. The driver
// strip is a different grain (a dimension, top 1), so it needs its own.
export default function buildQuery(formData: ProviderSpendCardFormData) {
  const {
    metric,
    share_metric: shareMetric,
    rate_metric: rateMetric,
    x_axis: xAxis,
    driver_dimension: driverDimension,
    sparkPeriods,
  } = formData;

  const metrics = [metric, shareMetric, rateMetric].filter(
    (item): item is QueryFormMetric => Boolean(item),
  );
  const periods =
    sparkPeriods && sparkPeriods > 0 ? sparkPeriods : DEFAULT_PERIODS;

  return buildQueryContext(formData, baseQueryObject => {
    const trendGroupby: QueryFormColumn[] = xAxis ? [xAxis] : [];
    const trendOrderBy = (
      xAxis ? [[xAxis, false]] : []
    ) as unknown as QueryFormOrderBy[];

    const trendQuery = {
      ...baseQueryObject,
      groupby: trendGroupby,
      metrics,
      orderby: trendOrderBy,
      row_limit: xAxis ? periods : 1,
    };

    if (!driverDimension) return [trendQuery];

    const driverOrderBy = [
      [metric, false],
    ] as unknown as QueryFormOrderBy[];

    return [
      trendQuery,
      {
        ...baseQueryObject,
        groupby: [driverDimension] as QueryFormColumn[],
        metrics: [metric],
        orderby: driverOrderBy,
        row_limit: 1,
      },
    ];
  });
}
