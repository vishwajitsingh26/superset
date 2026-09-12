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
  QueryFormColumn,
} from '../adapters/supersetAdapter';
import { CustomDateRangeFilterFormData } from '../types';

// The bounds dataset is a one-row view, so one row is all this control ever
// needs: the earliest and latest selectable date, fetched once per render.
export const BOUNDS_ROW_LIMIT = 1;

export default function buildQuery(formData: CustomDateRangeFilterFormData) {
  const { boundsStartColumn, boundsEndColumn } = formData;
  const columns: QueryFormColumn[] = [
    boundsStartColumn,
    boundsEndColumn,
  ].filter((column): column is QueryFormColumn => Boolean(column));

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      groupby: columns,
      metrics: [],
      row_limit: BOUNDS_ROW_LIMIT,
    },
  ]);
}
