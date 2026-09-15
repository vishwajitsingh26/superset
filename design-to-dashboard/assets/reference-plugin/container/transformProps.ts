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
import { ChartProps } from "../adapters/supersetAdapter";
import { CustomWrapperChartFormData, WrapperTab } from "./types";
import { WrapperChartProps } from "./WrapperChart";

interface WrapperOwnState {
  dashboardId?: number;
}

// Maps Superset's generic `ChartProps` into the typed props `<WrapperChart>`
// renders from. `wrapperFilters` and `filterValues` are always empty here --
// this directory implements the tab-hosting mechanism only, and there is no
// filters editor control to author `wrapper_filters` with (see `types.ts`).
// A plugin that adds that control would populate both from formData here,
// the same way `wrapper_tabs` is read below.
export default function transformProps(
  chartProps: ChartProps<CustomWrapperChartFormData>,
): WrapperChartProps {
  const { width, height, formData, ownState } = chartProps as ChartProps<
    CustomWrapperChartFormData
  > & { ownState?: WrapperOwnState };

  // Some Superset versions carry unregistered controls on `rawFormData`
  // rather than `formData`; reading both is what keeps `wrapper_tabs` visible
  // regardless of which one this build populated.
  const rawFormData = (chartProps as unknown as Record<string, unknown>)
    .rawFormData as Record<string, unknown> | undefined;
  const rawTabs =
    (rawFormData?.wrapper_tabs as unknown) ?? formData?.wrapper_tabs;
  const parsedTabs =
    typeof rawTabs === "string"
      ? (() => {
          try {
            return JSON.parse(rawTabs);
          } catch {
            return [];
          }
        })()
      : rawTabs;

  const tabs: WrapperTab[] = Array.isArray(parsedTabs)
    ? (parsedTabs as unknown[]).filter(
        (tab): tab is WrapperTab =>
          !!tab &&
          typeof tab === "object" &&
          typeof (tab as WrapperTab).id === "string" &&
          typeof (tab as WrapperTab).chartId === "number",
      )
    : [];

  return {
    width,
    height,
    dashboardId:
      (formData as unknown as Record<string, unknown>)?.dashboardId as
        | number
        | undefined ?? ownState?.dashboardId,
    tabs,
    wrapperFilters: [],
    filterValues: {},
  };
}
