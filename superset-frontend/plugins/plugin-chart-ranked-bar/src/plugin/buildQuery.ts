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
  QueryFormData,
  QueryFormMetric,
} from '@superset-ui/core';

const DEFAULT_ROW_LIMIT = 5;

/**
 * The ranking is a database concern, not a browser one: the top-N cut is sent
 * down as ORDER BY <metric> DESC + LIMIT so the client never sorts or slices.
 */
export default function buildQuery(formData: QueryFormData) {
  const {
    groupby,
    metric,
    row_limit: rowLimit,
  } = formData as QueryFormData & {
    groupby?: QueryFormColumn | QueryFormColumn[];
    metric?: QueryFormMetric;
    row_limit?: number;
  };

  const metrics: QueryFormMetric[] = metric ? [metric] : [];
  // `false` is the ascending flag, so this is descending: longest bar first.
  const orderby: [QueryFormMetric, boolean][] = metric ? [[metric, false]] : [];

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      groupby: ensureIsArray<QueryFormColumn>(groupby),
      metrics,
      orderby,
      row_limit: rowLimit ?? DEFAULT_ROW_LIMIT,
    },
  ]);
}
