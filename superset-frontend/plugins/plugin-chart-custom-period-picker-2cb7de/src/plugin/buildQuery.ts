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
  getColumnLabel,
  QueryFormColumn,
  QueryFormOrderBy,
} from '../adapters/supersetAdapter';
import { DEFAULT_ROW_LIMIT } from '../constants';
import { PeriodPickerFormData } from '../types';

// One query: the distinct values of the period column, newest first. The
// options list is derived from these rows, so no second request is needed.
export default function buildQuery(formData: PeriodPickerFormData) {
  const column = formData.x_axis;
  const rowLimit = formData.rowLimit ?? formData.row_limit ?? DEFAULT_ROW_LIMIT;

  if (!column) {
    return buildQueryContext(formData, baseQueryObject => [
      { ...baseQueryObject, groupby: [], metrics: [], row_limit: rowLimit },
    ]);
  }

  const groupby: QueryFormColumn[] = [column];
  const orderby: QueryFormOrderBy[] = [
    [getColumnLabel(column), false] as unknown as QueryFormOrderBy,
  ];

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      groupby,
      metrics: [],
      orderby,
      row_limit: rowLimit,
    },
  ]);
}
