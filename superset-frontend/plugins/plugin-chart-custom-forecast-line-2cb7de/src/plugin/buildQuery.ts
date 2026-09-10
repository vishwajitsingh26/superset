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
  QueryFormOrderBy,
} from '../adapters/supersetAdapter';
import { DEFAULT_ROW_LIMIT } from '../constants';
import { ForecastLineQueryFormData } from '../types';

// One query object: actual and forecast rows differ only by a dimension value,
// so both series sets come back in a single trip.
export default function buildQuery(formData: ForecastLineQueryFormData) {
  const { x_axis: xAxis, groupby, metric, row_limit: rowLimit } = formData;
  const dimensions = ensureIsArray<QueryFormColumn>(groupby);

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      columns: xAxis ? [xAxis, ...dimensions] : dimensions,
      metrics: metric ? [metric] : [],
      orderby: xAxis ? [[xAxis, true] as QueryFormOrderBy] : [],
      row_limit: rowLimit ?? DEFAULT_ROW_LIMIT,
      is_timeseries: false,
    },
  ]);
}
