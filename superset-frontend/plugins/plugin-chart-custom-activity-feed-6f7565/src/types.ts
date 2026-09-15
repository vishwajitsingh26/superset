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
import { QueryFormData } from './adapters/supersetAdapter';

export interface CustomActivityFeedStylesProps {
  height: number;
  width: number;
}

// Every control `controlPanel.ts` declares belongs here, as a plain column
// name string -- these are raw display columns, not aggregated metrics, so
// there is no adhoc-metric shape to carry.
export interface CustomActivityFeedCustomizeProps {
  titleColumn?: string;
  descriptionColumn?: string;
  severityColumn?: string;
  timestampColumn?: string;
  row_limit?: number | string;
  viewAllLabel?: string;
  viewAllUrl?: string;
}

export type CustomActivityFeedFormData = QueryFormData &
  CustomActivityFeedStylesProps &
  CustomActivityFeedCustomizeProps;

// Severity is read from whatever text the attached dataset carries; this
// is the small closed set of badge treatments the design actually draws.
export type SeverityKind = 'error' | 'info' | 'success' | 'default';

export interface ActivityItemData {
  key: string;
  title: string;
  description: string;
  timestamp: string;
  severity: SeverityKind;
}

export interface ActivityFeedProps {
  width: number;
  height: number;
  items: ActivityItemData[];
  viewAllLabel?: string;
  viewAllUrl?: string;
}
