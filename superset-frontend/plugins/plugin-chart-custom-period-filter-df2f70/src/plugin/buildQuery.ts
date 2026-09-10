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
  QueryFormMetric,
  buildQueryContext,
  ensureIsArray,
} from '../adapters/supersetAdapter';
import {
  DEFAULT_ROW_LIMIT,
  MAX_PERIOD_LABEL,
  MIN_PERIOD_LABEL,
} from '../constants';
import { PeriodFilterFormData } from '../types';

function boundsMetric(
  column: string,
  aggregate: 'MIN' | 'MAX',
  label: string,
): QueryFormMetric {
  return {
    expressionType: 'SIMPLE',
    column: { column_name: column },
    aggregate,
    label,
    hasCustomLabel: true,
  } as unknown as QueryFormMetric;
}

export default function buildQuery(formData: PeriodFilterFormData) {
  const dateColumn = formData.date_column ?? formData.dateColumn ?? '';
  const dimensions = ensureIsArray<QueryFormColumn>(formData.groupby);
  const rowLimit =
    formData.row_limit ?? formData.rowLimit ?? DEFAULT_ROW_LIMIT;

  return buildQueryContext(formData, baseQueryObject => {
    // Query 0: the min/max period bounds that populate the month dropdown.
    const bounds = {
      ...baseQueryObject,
      groupby: [],
      columns: [],
      metrics: dateColumn
        ? [
            boundsMetric(dateColumn, 'MIN', MIN_PERIOD_LABEL),
            boundsMetric(dateColumn, 'MAX', MAX_PERIOD_LABEL),
          ]
        : [],
      is_timeseries: false,
      row_limit: 1,
    };

    if (dimensions.length === 0) {
      return [bounds];
    }

    // Query 1: distinct values for the Filter panel. A different grain and
    // shape from the bounds row, so it cannot be derived from query 0.
    return [
      bounds,
      {
        ...baseQueryObject,
        groupby: dimensions,
        columns: dimensions,
        metrics: [],
        is_timeseries: false,
        row_limit: rowLimit,
      },
    ];
  });
}
