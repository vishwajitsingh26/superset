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
  ensureIsArray,
  QueryFormColumn,
} from '../adapters/supersetAdapter';
import { presentMetrics } from '../adapters/optionalMetrics';
import { CustomSpendingTrendChartFormData } from '../types';

export default function buildQuery(formData: CustomSpendingTrendChartFormData) {
  const { x_axis, groupby, metric, grain, row_limit } = formData;

  const groupbyCols = ensureIsArray<QueryFormColumn>(groupby);
  const columns: QueryFormColumn[] = x_axis
    ? [x_axis, ...groupbyCols]
    : groupbyCols;
  const metrics = presentMetrics([metric]);

  // `grain` is this chart's own Daily/Weekly/Monthly control -- it drives a
  // full requery (not renderTrigger) because the aggregation window itself
  // changes, unlike a colour or label tweak.
  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      columns,
      metrics,
      time_grain_sqla: grain || 'P1D',
      row_limit: Number(row_limit) || 1000,
    },
  ]);
}
