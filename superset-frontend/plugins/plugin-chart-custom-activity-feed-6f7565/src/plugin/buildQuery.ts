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
import { CustomActivityFeedFormData } from '../types';

const DEFAULT_ROW_LIMIT = 5;

// A literal feed of rows, not an aggregation: `columns` (raw select), no
// `metrics`, no groupby.
export default function buildQuery(formData: CustomActivityFeedFormData) {
  const {
    titleColumn,
    descriptionColumn,
    severityColumn,
    timestampColumn,
    row_limit,
  } = formData;

  const columns: QueryFormColumn[] = [
    titleColumn,
    descriptionColumn,
    severityColumn,
    timestampColumn,
  ].filter((column): column is string => Boolean(column));

  const orderby: [QueryFormColumn, boolean][] = timestampColumn
    ? [[timestampColumn, false]]
    : [];

  return buildQueryContext(formData, baseQueryObject => [
    {
      ...baseQueryObject,
      columns,
      metrics: [],
      orderby,
      row_limit: Number(row_limit) || DEFAULT_ROW_LIMIT,
    },
  ]);
}
