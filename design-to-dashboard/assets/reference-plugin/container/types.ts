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
import { QueryFormData } from "../adapters/supersetAdapter";

// A single tab inside the wrapper. It references an existing saved chart by
// id rather than embedding a query of its own -- the wrapper's whole job is
// hosting, not visualizing.
export interface WrapperTab {
  // Stable across reorders and renames, so `TabContent` can key on it instead
  // of on array position.
  id: string;
  // Existing saved Superset chart (slice) id.
  chartId: number;
  // Tab display label shown in the tab strip.
  label: string;
}

// Only the mechanism this exemplar actually implements: a single-select
// column filter whose value is turned into an `IN` clause and merged into
// every hosted chart's query. A time-grain filter or anything richer would
// need its own editor control, which does not exist in this directory --
// adding the type without the control would be inventing a feature nothing
// here can author.
export interface WrapperFilter {
  id: string;
  label: string;
  // Dataset column whose distinct values this filter constrains.
  column: string;
  default: string | string[] | null;
}

// Runtime selected values for the declared `WrapperFilter`s, keyed by filter
// id. Absent from the record until a viewer changes that filter's control.
export type WrapperFilterValues = Record<
  string,
  string | string[] | null | undefined
>;

// Slice formData for the wrapper plugin. `wrapper_tabs` is the only control
// this directory implements -- see `wrapperTabs.tsx`.
export interface CustomWrapperChartFormData extends QueryFormData {
  wrapper_tabs: WrapperTab[];
}
