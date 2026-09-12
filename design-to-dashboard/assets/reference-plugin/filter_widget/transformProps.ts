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
import { ChartProps, SetDataMaskHook } from "../adapters/supersetAdapter";
import {
  DEFAULT_GRAIN,
  DEFAULT_GRAIN_COUNTS,
  GRAIN_LABELS,
  GRAIN_ORDER,
} from "../constants";
import {
  GrainKey,
  GrainOption,
  PeriodFilterFormData,
  PeriodFilterProps,
  PeriodFilterValue,
} from "../types";
import { MAX_PERIOD_LABEL, MIN_PERIOD_LABEL } from "./buildQuery";
import { buildMonthOptions, parsePeriod } from "../utils/parseBounds";

function getRowValue(row: Record<string, unknown>, key: string): unknown {
  if (key in row) return row[key];
  const lower = key.toLowerCase();
  const match = Object.keys(row).find((k) => k.toLowerCase() === lower);
  return match ? row[match] : undefined;
}

function readField(
  raw: Record<string, unknown> | undefined,
  formData: Record<string, unknown>,
  snake: string,
  camel: string,
): unknown {
  return raw?.[snake] ?? formData?.[camel];
}

function toCount(value: unknown, grain: GrainKey): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0
    ? Math.floor(n)
    : DEFAULT_GRAIN_COUNTS[grain];
}

function buildGrainOptions(
  enabled: GrainKey[],
  counts: Record<GrainKey, number>,
): GrainOption[] {
  const enabledSet = new Set(enabled);
  return GRAIN_ORDER.filter((g) => enabledSet.has(g)).map((key) => ({
    key,
    label: GRAIN_LABELS[key],
    count: counts[key],
  }));
}

export default function transformProps(
  chartProps: ChartProps<PeriodFilterFormData>,
): PeriodFilterProps {
  const { width, height, queriesData, hooks, filterState } =
    chartProps as ChartProps<PeriodFilterFormData> & {
      hooks: { setDataMask?: SetDataMaskHook };
      filterState?: { value?: PeriodFilterValue | null };
    };

  const raw = (chartProps as unknown as Record<string, unknown>).rawFormData as
    | Record<string, unknown>
    | undefined;
  const formData = chartProps.formData as unknown as Record<string, unknown>;

  const dateColumn =
    (readField(raw, formData, "date_column", "dateColumn") as string) ?? "";

  const enabledRaw = (readField(
    raw,
    formData,
    "enabled_grains",
    "enabledGrains",
  ) ?? GRAIN_ORDER) as GrainKey[];
  const enabled = Array.isArray(enabledRaw) ? enabledRaw : GRAIN_ORDER;

  const counts: Record<GrainKey, number> = {
    daily: toCount(
      readField(raw, formData, "daily_count", "dailyCount"),
      "daily",
    ),
    weekly: toCount(
      readField(raw, formData, "weekly_count", "weeklyCount"),
      "weekly",
    ),
    monthly: toCount(
      readField(raw, formData, "monthly_count", "monthlyCount"),
      "monthly",
    ),
    quarterly: toCount(
      readField(raw, formData, "quarterly_count", "quarterlyCount"),
      "quarterly",
    ),
    yearly: toCount(
      readField(raw, formData, "yearly_count", "yearlyCount"),
      "yearly",
    ),
  };

  const grainOptions = buildGrainOptions(enabled, counts);

  const defaultGrain =
    (readField(raw, formData, "default_grain", "defaultGrain") as GrainKey) ??
    DEFAULT_GRAIN;

  const data = (queriesData?.[0]?.data ?? []) as Record<string, unknown>[];
  const boundsRow = data[0] ?? {};
  const min = parsePeriod(getRowValue(boundsRow, MIN_PERIOD_LABEL));
  const max = parsePeriod(getRowValue(boundsRow, MAX_PERIOD_LABEL));
  const monthOptions = min && max ? buildMonthOptions(min, max) : [];

  const sliceId =
    (raw?.slice_id as number) ?? (formData?.sliceId as number) ?? undefined;

  return {
    height,
    width,
    monthOptions,
    grainOptions,
    selectedValue: (filterState?.value as PeriodFilterValue) ?? null,
    defaultGrain,
    dateColumn,
    setDataMask: hooks?.setDataMask ?? (() => {}),
    sliceId,
    isRefreshing: (chartProps as unknown as Record<string, unknown>)
      .isRefreshing as boolean | undefined,
  };
}
