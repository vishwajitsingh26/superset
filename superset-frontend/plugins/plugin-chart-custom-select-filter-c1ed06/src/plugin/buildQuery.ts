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
  buildQueryContext,
  ensureIsArray,
} from '../adapters/supersetAdapter';
import { DEFAULT_ROW_LIMIT } from '../constants';
import { SelectFilterFormData } from '../types';

// One query object: the distinct values of the configured column. The option
// list is the only thing this widget renders, so nothing else is fetched.
export default function buildQuery(formData: SelectFilterFormData) {
  const { groupby, rowLimit, row_limit: snakeRowLimit } = formData;
  const column = ensureIsArray<QueryFormColumn>(groupby)[0];

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      // The query object uses `columns`; `groupby` is form-data vocabulary and
      // is ignored here, which left both columns and metrics empty and made
      // Superset reject the whole thing with "Empty query?".
      columns: column ? [column] : [],
      groupby: column ? [column] : [],
      metrics: [],
      row_limit: rowLimit ?? snakeRowLimit ?? DEFAULT_ROW_LIMIT,
    },
  ]);
}
