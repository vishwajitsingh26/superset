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
import { ChartProps, DataRecord } from '../adapters/supersetAdapter';
import { classifySeverity } from '../utils/severity';
import {
  ActivityFeedProps,
  ActivityItemData,
  CustomActivityFeedFormData,
} from '../types';

export default function transformProps(
  chartProps: ChartProps<CustomActivityFeedFormData>,
): ActivityFeedProps {
  const { width, height, formData, queriesData } = chartProps;
  const {
    titleColumn,
    descriptionColumn,
    severityColumn,
    timestampColumn,
    viewAllLabel,
    viewAllUrl,
  } = formData;

  const rows: DataRecord[] = queriesData?.[0]?.data ?? [];

  const items: ActivityItemData[] = rows.map((row, index) => {
    const rawSeverity = severityColumn ? row[severityColumn] : null;
    const severityText =
      rawSeverity === null || rawSeverity === undefined
        ? null
        : String(rawSeverity);
    return {
      key: String(index),
      title: titleColumn ? String(row[titleColumn] ?? '') : '',
      description: descriptionColumn
        ? String(row[descriptionColumn] ?? '')
        : '',
      timestamp: timestampColumn ? String(row[timestampColumn] ?? '') : '',
      severity: classifySeverity(severityText),
    };
  });

  return {
    width: width ?? 0,
    height: height ?? 0,
    items,
    viewAllLabel: viewAllLabel || undefined,
    viewAllUrl: viewAllUrl || undefined,
  };
}
