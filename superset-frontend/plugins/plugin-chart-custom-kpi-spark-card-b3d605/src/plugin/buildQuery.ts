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
  isPhysicalColumn,
  QueryFormColumn,
  QueryFormMetric,
} from '../adapters/supersetAdapter';
import { CustomKpiSparkCardFormData } from '../types';
import { DEFAULT_ROW_LIMIT } from '../utils/constants';

// One query object. The card's value, its change and the sparkline series all
// come out of the same rows, so a second query would only save a `reduce`.
export default function buildQuery(formData: CustomKpiSparkCardFormData) {
  const { x_axis: xAxis, metric, deltaMetric } = formData;
  const timeGrain = formData.time_grain_sqla;

  const metrics: QueryFormMetric[] = [metric, deltaMetric].filter(
    (item): item is QueryFormMetric => Boolean(item),
  );

  const columns: QueryFormColumn[] = [];
  if (xAxis) {
    columns.push(
      isPhysicalColumn(xAxis) && timeGrain
        ? {
            timeGrain,
            columnType: 'BASE_AXIS',
            expressionType: 'SQL',
            sqlExpression: xAxis,
            label: xAxis,
          }
        : xAxis,
    );
  }

  // Chronological order comes from the database, so the browser never sorts.
  const orderby: [QueryFormMetric, boolean][] =
    typeof xAxis === 'string' ? [[xAxis, true]] : [];

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      columns,
      groupby: [],
      metrics,
      orderby: orderby.length > 0 ? orderby : baseQueryObject.orderby,
      row_limit: Number(formData.row_limit) || DEFAULT_ROW_LIMIT,
    },
  ]);
}
