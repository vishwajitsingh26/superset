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
import type { QueryFormData } from './adapters/supersetAdapter';

export type SpendingTrendView = 'Daily' | 'Weekly' | 'Monthly';

// Every control `controlPanel.ts` declares belongs here.
export interface CustomSpendingTrendWrapperCustomizeProps {
  // Filled by stage D once the hosted chart (c11, "Spending Trend — Stacked
  // Area") has a real persisted chart id. TextControl values can arrive as
  // string, number or unset, so this is read defensively in transformProps.
  childChartId?: number | string | null;
  defaultView?: SpendingTrendView;
}

export type CustomSpendingTrendWrapperFormData = QueryFormData &
  CustomSpendingTrendWrapperCustomizeProps;

export interface CustomSpendingTrendWrapperProps {
  width: number;
  height: number;
  childChartId: number | null;
  defaultView: SpendingTrendView;
  isInView: boolean;
}
