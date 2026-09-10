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
import { FilterPanelFormData } from '../types';

// One query for every field: the distinct combinations are grouped once and
// split into per-field option lists in transformProps.
export default function buildQuery(formData: FilterPanelFormData) {
  const columns = ensureIsArray<QueryFormColumn>(formData.groupby);

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      groupby: columns,
      metrics: [],
      orderby: [],
      row_limit:
        formData.rowLimit ?? formData.row_limit ?? DEFAULT_ROW_LIMIT,
    },
  ]);
}
