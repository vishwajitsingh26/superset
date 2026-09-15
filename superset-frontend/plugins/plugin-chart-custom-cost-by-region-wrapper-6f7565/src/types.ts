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

// Two fixed slots, not a dynamic list: this card's own crop shows exactly
// one map and one list, side by side, so the config surface matches that --
// a chart id per slot -- rather than an editable list of tabs.
export interface CustomCostByRegionWrapperCustomizeProps {
  mapChartId?: number;
  listChartId?: number;
}

export interface CustomCostByRegionWrapperStylesProps {
  width: number;
  height: number;
}

export type CustomCostByRegionWrapperFormData = QueryFormData &
  CustomCostByRegionWrapperCustomizeProps;

export type CustomCostByRegionWrapperProps =
  CustomCostByRegionWrapperStylesProps &
    CustomCostByRegionWrapperCustomizeProps;
