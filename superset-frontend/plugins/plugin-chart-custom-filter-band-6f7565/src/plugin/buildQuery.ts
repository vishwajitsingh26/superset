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
import { CustomFilterBandFormData } from '../types';

const DEFAULT_ROW_LIMIT = 1000;
const DEFAULT_TYPE_COLUMN = 'filter_type';
const DEFAULT_VALUE_COLUMN = 'filter_value';

// One query returns every (type, value) row for all four dropdowns; each is
// split into its own options client-side in transformProps, so the widget
// asks the database once per render rather than four times.
export default function buildQuery(formData: CustomFilterBandFormData) {
  const typeColumn: QueryFormColumn =
    formData.typeColumn || DEFAULT_TYPE_COLUMN;
  const valueColumn: QueryFormColumn =
    formData.valueColumn || DEFAULT_VALUE_COLUMN;
  const rowLimit = Number(formData.row_limit) || DEFAULT_ROW_LIMIT;

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      groupby: [typeColumn, valueColumn],
      metrics: [],
      row_limit: rowLimit,
      orderby: [],
    },
  ]);
}
