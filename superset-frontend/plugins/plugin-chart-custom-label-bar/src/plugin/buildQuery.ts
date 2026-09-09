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
import { CustomLabelBarFormData } from '../types';

// One query object: the ranking, the cut and the ordering all happen in the
// database so the browser never sorts or slices.
export default function buildQuery(formData: CustomLabelBarFormData) {
  const { groupby, metric, row_limit: rowLimit } = formData;
  const columns = ensureIsArray<QueryFormColumn>(groupby).slice(0, 1);
  const metrics = metric ? [metric] : [];
  const orderby: QueryFormOrderBy[] = metric ? [[metric, false]] : [];

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      columns,
      groupby: columns,
      metrics,
      orderby,
      row_limit: Number(rowLimit) || DEFAULT_ROW_LIMIT,
    },
  ]);
}
