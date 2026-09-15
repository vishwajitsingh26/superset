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
// Written for every plugin and not replaceable. A saved chart may hold an
// empty metric in any control, whatever its validators say, and
// `getMetricLabel` throws on one -- so read every metric control through
// these and draw what is present instead of failing the whole dashboard.
import { getMetricLabel } from './supersetAdapter';
import type { DataRecord, QueryFormMetric } from './supersetAdapter';

export type OptionalMetric = QueryFormMetric | null | undefined;

export function hasMetric(metric: OptionalMetric): metric is QueryFormMetric {
  return metric !== null && metric !== undefined && metric !== '';
}

export function metricLabelOrNull(metric: OptionalMetric): string | null {
  return hasMetric(metric) ? getMetricLabel(metric) : null;
}

export function presentMetrics(metrics: OptionalMetric[]): QueryFormMetric[] {
  return metrics.filter(hasMetric);
}

export function metricValue(
  row: DataRecord | undefined,
  metric: OptionalMetric,
): DataRecord[string] {
  const label = metricLabelOrNull(metric);
  return label === null || !row ? null : (row[label] ?? null);
}
