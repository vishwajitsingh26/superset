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
import { presentMetrics } from '../adapters/optionalMetrics';
import { CustomTableWithBarFormData } from '../types';
import { DEFAULT_ROW_LIMIT } from '../constants';

export default function buildQuery(formData: CustomTableWithBarFormData) {
  const { groupby, metric, secondaryMetric, rowLimit, row_limit } = formData;

  const allGroupby = ensureIsArray<QueryFormColumn>(groupby);
  // A saved chart can hold an empty metric in either slot; only the present
  // ones are ever sent to the database.
  const metrics = presentMetrics([metric, secondaryMetric]);
  const limit = Number(rowLimit ?? row_limit) || DEFAULT_ROW_LIMIT;

  // Sort by the primary metric descending, matching the design's own row
  // order (largest spend first); untouched when no metric is configured.
  const orderby: QueryFormOrderBy[] = metrics.length
    ? [[metrics[0], false]]
    : [];

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      groupby: allGroupby,
      metrics,
      row_limit: limit,
      orderby: orderby.length ? orderby : baseQueryObject.orderby,
    },
  ]);
}
