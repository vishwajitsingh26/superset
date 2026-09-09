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
import { QueryFormData, QueryFormMetric } from '@superset-ui/core';

export interface LabeledHbarStylesProps {
  height: number;
  width: number;
}

/**
 * Presentation controls. ChartProps camel-cases form data, so these names are
 * the camelCase form of the snake_case control names declared in controlPanel.
 */
export interface LabeledHbarCustomizeProps {
  /** Optional in-chart header. Left empty when the dashboard card supplies it. */
  headerText: string;
  /** Flat fill applied to every bar. */
  barColor: string;
  /** Bar height in pixels. */
  barThickness: number;
  /** Unit annotation appended to the formatted value, e.g. "M". */
  valueSuffix: string;
  /** d3 format string applied to the value label. */
  numberFormat: string;
}

/** Raw (snake_case) form data as seen by buildQuery. */
export type LabeledHbarQueryFormData = QueryFormData & {
  series?: string;
  metric?: QueryFormMetric;
};

/** Camel-cased form data as seen by transformProps. */
export type LabeledHbarTransformFormData = LabeledHbarQueryFormData &
  Partial<LabeledHbarCustomizeProps>;

/** One rendered row: everything the component needs, already shaped. */
export interface LabeledHbarDatum {
  key: string;
  label: string;
  value: number;
  formattedValue: string;
  /** Bar length as a percentage of the longest bar. */
  widthPercent: number;
}

export type LabeledHbarProps = LabeledHbarStylesProps &
  LabeledHbarCustomizeProps & {
    data: LabeledHbarDatum[];
    /** Character width of the widest value label, used to reserve its gutter. */
    valueColumnChars: number;
  };
