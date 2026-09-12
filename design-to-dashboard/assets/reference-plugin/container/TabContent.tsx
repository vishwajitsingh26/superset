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
// @ts-ignore – React is needed at runtime for JSX
import React, { FC, useEffect, useMemo, useRef } from "react";
import { useDispatch, useSelector, useStore } from "react-redux";
import ChartContainer from "src/components/Chart/ChartContainer";
import { addChart, triggerQuery } from "src/components/Chart/chartAction";
import { chart as initChart } from "src/components/Chart/chartReducer";
import { PLACEHOLDER_DATASOURCE } from "src/dashboard/constants";
// ChartContainer's props are properly typed upstream. Naming those types here
// is what removes the casts: a local state shape that says `unknown` has to be
// forced into them, and `as any` is how that was done.
import type { ChartState, ChartStatus, Datasource } from "src/explore/types";
import { fetchDatasourceMetadata } from "src/dashboard/actions/datasources";
import { Empty } from "@superset-ui/core/components";
import { SupersetClient } from "@superset-ui/core";
import type { JsonObject, QueryFormData } from "@superset-ui/core";
import { styled, t, ExtraFormData } from "../../adapters/supersetAdapter";
import { WrapperFilter, WrapperFilterValues } from "../../types";
import {
  mergeExtraFormData,
  wrapperFilterValuesAsExtraFormData,
} from "../../utils/extraFormData";

const NATIVE_FILTER_PREFIX = "NATIVE_FILTER-";

interface TabContentProps {
  chartId: number;
  dashboardId?: number;
  width: number;
  height: number;
  isInView: boolean;
  wrapperFilters: WrapperFilter[];
  filterValues: WrapperFilterValues;
  hideLoading?: boolean;
}

interface RootState {
  charts: Record<
    number,
    {
      id: number;
      chartStatus?: ChartStatus;
      chartUpdateStartTime?: number;
      chartUpdateEndTime?: number;
      chartAlert?: string | null;
      chartStackTrace?: string | null;
      queriesResponse?: ChartState["queriesResponse"];
      triggerQuery?: boolean;
      annotationData?: JsonObject;
      latestQueryFormData?: QueryFormData;

      queryController?: AbortController | null;
    }
  >;
  sliceEntities?: {
    slices?: Record<
      number,
      { slice_id: number; slice_name: string; viz_type: string }
    >;
  };
  datasources?: Record<string, Datasource>;
  dataMask?: Record<
    string,
    | {
        id?: string;
        ownState?: JsonObject;
        filterState?: unknown;
        extraFormData?: ExtraFormData;
      }
    | undefined
  >;
  dashboardInfo?: {
    common?: { conf?: { SUPERSET_WEBSERVER_TIMEOUT?: number } };
    crossFiltersEnabled?: boolean;
  };
  dashboardState?: { datasetsStatus?: "loading" | "error" | "complete" };
}

const Root = styled.div<{ $minHeight?: number; $autoHeight?: boolean }>`
  position: relative;
  width: 100%;
  min-height: ${({ $autoHeight, $minHeight }) =>
    $autoHeight ? "0" : $minHeight ? `${$minHeight}px` : "0"};
  height: ${({ $autoHeight }) => ($autoHeight ? "auto" : "fit-content")};
  max-height: ${({ $minHeight }) => ($minHeight ? `${$minHeight}px` : "none")};
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;

  // Allow the Superset Chart wrapper to shrink to content
  .chart-container {
    ${({ $autoHeight, $minHeight }) =>
      $autoHeight
        ? `
      min-height: 0 !important;
      height: auto !important;
      max-height: ${$minHeight ? `${$minHeight}px` : "none"} !important;
    `
        : ""}
  }

  .slice_container {
    ${({ $autoHeight, $minHeight }) =>
      $autoHeight
        ? `
      justify-content: flex-start !important;
      height: auto !important;
      max-height: ${$minHeight ? `${$minHeight}px` : "none"} !important;
    `
        : ""}
  }

  > * {
    margin: 0;
    padding: 0;
  }
`;

const Centered = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const noop = () => {};

function useBootstrapEmbeddedChart(
  chartId: number,
  hasChart: boolean,
  hasSlice: boolean,
) {
  const dispatch = useDispatch();
  const bootstrappedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (hasChart && hasSlice) return undefined;
    if (bootstrappedRef.current.has(chartId)) return undefined;
    bootstrappedRef.current.add(chartId);

    const controller = new AbortController();

    (async () => {
      try {
        const response = await SupersetClient.get({
          endpoint: `/api/v1/chart/${chartId}`,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;

        const chartData = (response.json as Record<string, unknown>).result as
          | Record<string, unknown>
          | undefined;
        if (!chartData) return;

        const params =
          typeof chartData.params === "string"
            ? JSON.parse(chartData.params)
            : chartData.params || {};
        const datasourceId = chartData.datasource_id as number;
        const datasourceType = chartData.datasource_type as string;
        const datasourceKey = `${datasourceId}__${datasourceType}`;

        const formData = {
          ...params,
          slice_id: chartId,
          datasource: datasourceKey,
        };

        if (!hasChart) {
          dispatch(
            addChart(
              {
                ...initChart,
                id: chartId,
                // 6.1 renamed this on ChartState; `form_data` is the 6.0 name
                // and is rejected by the type checker.
                latestQueryFormData: formData,
              },
              chartId,
            ),
          );
        }

        if (!hasSlice) {
          dispatch({
            type: "ADD_SLICES",
            payload: {
              slices: {
                [chartId]: {
                  slice_id: chartId,
                  slice_name: (chartData.slice_name as string) || "",
                  slice_url: (chartData.url as string) || "",
                  form_data: formData,
                  viz_type:
                    (chartData.viz_type as string) || params.viz_type || "",
                  datasource: datasourceKey,
                  description: (chartData.description as string) || "",
                  description_markeddown:
                    (chartData.description_markeddown as string) || "",
                },
              },
            },
          });
        }

        if (datasourceKey) {
          dispatch(fetchDatasourceMetadata(datasourceKey) as unknown as never);
        }
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        bootstrappedRef.current.delete(chartId);
      }
    })();

    return (): void => {
      controller.abort();
    };
  }, [chartId, hasChart, hasSlice, dispatch]);
}

function useAbortChartDataOnUnmount(chartId: number) {
  const { getState } = useStore();

  useEffect(
    () => () => {
      const state = getState() as RootState;
      const controller = state.charts?.[chartId]?.queryController ?? null;
      controller?.abort();
    },
    [chartId, getState],
  );
}

const TabContent: FC<TabContentProps> = ({
  chartId,
  dashboardId,
  width,
  height,
  isInView,
  wrapperFilters,
  filterValues,
  hideLoading,
}) => {
  const chart = useSelector((s: RootState) => s.charts?.[chartId]);
  const slice = useSelector(
    (s: RootState) => s.sliceEntities?.slices?.[chartId],
  );

  useBootstrapEmbeddedChart(chartId, !!chart, !!slice);

  // Abort in-flight chart data fetch on tab switch (component unmount).
  useAbortChartDataOnUnmount(chartId);

  const rootRef = useRef<HTMLDivElement>(null);

  // For custom_hierarchy_table: collapse .
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    if (slice?.viz_type !== "custom_hierarchy_table") return;
    const chartContainer = root.querySelector<HTMLElement>(".chart-container");
    if (!chartContainer) return;
    const rendered =
      chart?.chartStatus === "rendered" || chart?.chartStatus === "success";
    chartContainer.style.minHeight = rendered ? "auto" : `${height}px`;
  });

  const datasource = useSelector((s: RootState) => {
    const formData = chart?.latestQueryFormData;
    const datasourceKey = formData?.datasource;
    if (
      typeof datasourceKey === "string" &&
      s.datasources &&
      s.datasources[datasourceKey]
    ) {
      return s.datasources[datasourceKey];
    }
    return PLACEHOLDER_DATASOURCE;
  });

  const dataMaskEntry = useSelector((s: RootState) => s.dataMask?.[chartId]);

  const nativeFiltersJson = useSelector((s: RootState) => {
    const dm = s.dataMask;
    if (!dm) return "";
    let merged: ExtraFormData = {};
    Object.entries(dm).forEach(([key, entry]) => {
      if (key === String(chartId)) return;
      const hasExtraFormData =
        entry?.extraFormData && Object.keys(entry.extraFormData).length > 0;
      if (!hasExtraFormData) return;
      const isNativeFilter = key.startsWith(NATIVE_FILTER_PREFIX);
      const isCrossFilter = /^\d+$/.test(key);
      if (isNativeFilter || isCrossFilter) {
        merged = mergeExtraFormData(merged, entry!.extraFormData!);
      }
    });
    return Object.keys(merged).length > 0 ? JSON.stringify(merged) : "";
  });

  const nativeFiltersExtraFormData: ExtraFormData | undefined = useMemo(
    () => (nativeFiltersJson ? JSON.parse(nativeFiltersJson) : undefined),
    [nativeFiltersJson],
  );

  const timeout = useSelector(
    (s: RootState) =>
      s.dashboardInfo?.common?.conf?.SUPERSET_WEBSERVER_TIMEOUT ?? 60,
  );

  const emitCrossFilters = useSelector(
    (s: RootState) => !!s.dashboardInfo?.crossFiltersEnabled,
  );

  const datasetsStatus = useSelector(
    (s: RootState) => s.dashboardState?.datasetsStatus,
  );

  const ready = !!chart && !!slice;
  const dispatch = useDispatch();
  const hasFiredInitialQuery = useRef(false);
  useEffect(() => {
    if (ready && !hasFiredInitialQuery.current) {
      hasFiredInitialQuery.current = true;

      if (chart.triggerQuery) return;

      const hasLiveRequest =
        chart.chartStatus === "loading" &&
        chart.queryController &&
        !chart.queryController.signal.aborted;
      if (hasLiveRequest) return;

      dispatch(triggerQuery(true, chartId));
    }
  }, [ready, chartId, dispatch]);

  // Re-query when native/cross-filter values change (skip initial mount).
  const prevNativeFiltersRef = useRef(nativeFiltersJson);
  const nativeFilterMountedRef = useRef(false);
  useEffect(() => {
    if (!ready) return;
    if (prevNativeFiltersRef.current !== nativeFiltersJson) {
      prevNativeFiltersRef.current = nativeFiltersJson;
      if (nativeFilterMountedRef.current) {
        dispatch(triggerQuery(true, chartId));
      }
    }
    nativeFilterMountedRef.current = true;
  }, [nativeFiltersJson, ready, chartId, dispatch]);

  // Re-query when wrapper-level filter selections change (skip initial mount).
  const wrapperFilterSignature = useMemo(
    () =>
      JSON.stringify(
        wrapperFilters.length > 0
          ? wrapperFilterValuesAsExtraFormData(wrapperFilters, filterValues)
          : {},
      ),
    [wrapperFilters, filterValues],
  );
  const prevWrapperSignatureRef = useRef(wrapperFilterSignature);
  const wrapperFilterMountedRef = useRef(false);
  useEffect(() => {
    if (!ready) return;
    if (prevWrapperSignatureRef.current !== wrapperFilterSignature) {
      prevWrapperSignatureRef.current = wrapperFilterSignature;
      if (wrapperFilterMountedRef.current) {
        dispatch(triggerQuery(true, chartId));
      }
    }
    wrapperFilterMountedRef.current = true;
  }, [wrapperFilterSignature, ready, chartId, dispatch]);

  const formData = useMemo<QueryFormData | null>(() => {
    if (!chart || !slice) return null;

    const wrapperExtra: ExtraFormData =
      wrapperFilters.length > 0
        ? wrapperFilterValuesAsExtraFormData(wrapperFilters, filterValues)
        : {};

    const baseExtra = (chart.latestQueryFormData?.extra_form_data ??
      {}) as ExtraFormData;

    let mergedExtra = baseExtra;
    if (nativeFiltersExtraFormData) {
      mergedExtra = mergeExtraFormData(mergedExtra, nativeFiltersExtraFormData);
    }
    mergedExtra = mergeExtraFormData(mergedExtra, wrapperExtra);

    return {
      ...(chart.latestQueryFormData ?? {}),
      slice_id: slice.slice_id,
      viz_type: slice.viz_type,
      dashboardId,
      extra_form_data: mergedExtra,
    };
  }, [
    chart,
    slice,
    dashboardId,
    wrapperFilters,
    filterValues,
    nativeFiltersExtraFormData,
  ]);

  if (!ready || !formData) {
    if (hideLoading) {
      return (
        <Root
          $minHeight={height}
          ref={rootRef}
          data-test={`wrapper-tab-${chartId}`}
        />
      );
    }
    return (
      <Root
        $minHeight={height}
        ref={rootRef}
        data-test={`wrapper-tab-${chartId}`}
      />
    );
  }

  if (!chart.id) {
    return (
      <Root
        $minHeight={height}
        ref={rootRef}
        data-test={`wrapper-tab-${chartId}`}
      >
        <Centered>
          <Empty description={t("Chart not available")} />
        </Centered>
      </Root>
    );
  }

  return (
    <Root
      $minHeight={height}
      $autoHeight={
        slice.viz_type === "custom_hierarchy_table" &&
        (chart.chartStatus === "rendered" || chart.chartStatus === "success")
      }
      ref={rootRef}
      data-test={`wrapper-tab-${chartId}`}
      data-test-chart-id={chartId}
      data-test-viz-type={slice.viz_type}
    >
      <ChartContainer
        width={width}
        height={height}
        addFilter={noop}
        onFilterMenuOpen={noop}
        onFilterMenuClose={noop}
        annotationData={chart.annotationData}
        chartAlert={chart.chartAlert ?? undefined}
        chartId={chartId}
        chartStatus={chart.chartStatus}
        datasource={datasource}
        dashboardId={dashboardId}
        initialValues={{}}
        formData={formData}
        ownState={dataMaskEntry?.ownState}
        queriesResponse={chart.queriesResponse}
        timeout={timeout}
        triggerQuery={chart.triggerQuery}
        vizType={slice.viz_type}
        setControlValue={noop}
        datasetsStatus={datasetsStatus}
        isInView={isInView}
        emitCrossFilters={emitCrossFilters}
      />
    </Root>
  );
};

export default TabContent;
