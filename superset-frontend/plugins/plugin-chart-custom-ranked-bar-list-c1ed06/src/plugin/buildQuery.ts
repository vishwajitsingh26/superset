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
  QueryFormOrderBy,
  buildQueryContext,
  ensureIsArray,
} from '../adapters/supersetAdapter';
import { DEFAULT_MAX_ITEMS } from '../constants';
import { RankedBarListQueryFormData } from '../types';

// One query object: the database ranks and truncates so the browser never has
// to sort a full result set.
export default function buildQuery(formData: RankedBarListQueryFormData) {
  const { groupby, metric, maxItems } = formData;
  const dimensions = ensureIsArray<QueryFormColumn>(groupby);
  const limit =
    typeof maxItems === 'number' && maxItems > 0 ? maxItems : DEFAULT_MAX_ITEMS;

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      groupby: dimensions,
      metrics: metric ? [metric] : [],
      orderby: metric ? ([[metric, false]] as QueryFormOrderBy[]) : [],
      row_limit: limit,
    },
  ]);
}
