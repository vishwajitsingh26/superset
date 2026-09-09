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
import { QueryFormData } from '@superset-ui/core';

export interface RankedBarStylesProps {
  height: number;
  width: number;
}

export interface RankedBarCustomizeProps {
  /** Optional in-card title. Left empty when the dashboard header carries it. */
  cardTitle: string;
  /** Fill colour of every bar; the design uses a single series. */
  barColor: string;
  /** Bar height in pixels. */
  barThickness: number;
  /** d3-format string applied to the metric value. */
  numberFormat: string;
  /** Magnitude suffix appended after the formatted value, e.g. "M". */
  valueSuffix: string;
  /** Draw the card border. Off by default: the dashboard card already has one. */
  showCardBorder: boolean;
}

/** Precomputed inline style so the component never derives layout at render. */
export interface BarStyle {
  width: string;
}

export interface RankedBarDatum {
  /** Stable key for reconciliation. */
  key: string;
  /** Category label, drawn above its own bar. */
  label: string;
  /** Raw metric value, kept for ordering and title attributes. */
  value: number;
  /** Metric value formatted for display, e.g. "1,751M". */
  valueLabel: string;
  /** Bar length as a share of the longest bar, 0..1. */
  fraction: number;
  /** Width of the bar, already expressed in CSS. */
  barStyle: BarStyle;
}

export type RankedBarQueryFormData = QueryFormData & RankedBarCustomizeProps;

export type RankedBarProps = RankedBarStylesProps &
  RankedBarCustomizeProps & {
    data: RankedBarDatum[];
    emptyMessage: string;
  };
