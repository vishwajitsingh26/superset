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
  ensureIsArray,
} from '../adapters/supersetAdapter';
import { DEFAULT_ROW_LIMIT, TREND_ROW_LIMIT } from '../constants';
import { SpendTableQueryFormData } from '../types';

export default function buildQuery(formData: SpendTableQueryFormData) {
  const groupby = ensureIsArray<QueryFormColumn>(formData.groupby);
  const provider = ensureIsArray<QueryFormColumn>(formData.providerColumn)[0];
  const trendColumn = ensureIsArray<QueryFormColumn>(formData.trendColumn)[0];
  const { metric, momMetric } = formData;
  const metrics: QueryFormMetric[] = [];
  if (metric) metrics.push(metric);
  if (momMetric) metrics.push(momMetric);
  const rowLimit = formData.rowLimit ?? formData.row_limit ?? DEFAULT_ROW_LIMIT;
  const orderby: QueryFormOrderBy[] = metric
    ? ([[metric, false]] as QueryFormOrderBy[])
    : [];

  return buildQueryContext(formData, baseQueryObject => {
    const main = {
      ...baseQueryObject,
      groupby: [...groupby, ...(provider ? [provider] : [])],
      metrics,
      orderby,
      row_limit: rowLimit,
    };
    // A second query only for the sparkline: a different grain than the table.
    if (!trendColumn || !groupby[0] || !metric) {
      return [main];
    }
    return [
      main,
      {
        ...baseQueryObject,
        groupby: [groupby[0], trendColumn],
        metrics: [metric],
        orderby: [[trendColumn, true]] as QueryFormOrderBy[],
        row_limit: TREND_ROW_LIMIT,
      },
    ];
  });
}
