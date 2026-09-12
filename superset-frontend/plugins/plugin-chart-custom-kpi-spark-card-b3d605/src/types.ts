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
import {
  QueryFormColumn,
  QueryFormData,
  QueryFormMetric,
} from './adapters/supersetAdapter';

// The design colours a fall in spend green: direction is read as good or bad,
// not as sign. This control is the mechanism for that.
export type DeltaSemantics =
  | 'decrease_is_good'
  | 'increase_is_good'
  | 'neutral';

export type DeltaDirection = 'up' | 'down' | 'flat';

export type DeltaTone = 'favorable' | 'unfavorable' | 'neutral';

export type KpiIconGlyph = 'cloud' | 'currency' | 'trend' | 'server';

// Every control `controlPanel.ts` declares belongs here, so the component and
// `transformProps` read them by name and typed rather than through a cast.
export interface CustomKpiSparkCardCustomizeProps {
  x_axis?: QueryFormColumn;
  metric?: QueryFormMetric;
  deltaMetric?: QueryFormMetric;
  cardLabel?: string;
  subCaption?: string;
  iconGlyph?: KpiIconGlyph;
  accentColor?: string;
  favorableColor?: string;
  unfavorableColor?: string;
  valueFormat?: string;
  percentFormat?: string;
  deltaSemantics?: DeltaSemantics;
  showSparkline?: boolean;
}

export type CustomKpiSparkCardFormData = QueryFormData &
  CustomKpiSparkCardCustomizeProps;

// Sparkline geometry normalised to 0..1 in both axes by `transformProps`, so
// the component only multiplies by its own box.
export interface SparkPoint {
  x: number;
  y: number;
}

export interface CustomKpiSparkCardProps {
  width: number;
  height: number;
  hasMetric: boolean;
  hasData: boolean;
  label: string;
  valueText: string;
  deltaText: string | null;
  deltaDirection: DeltaDirection;
  deltaTone: DeltaTone;
  subCaption: string;
  iconGlyph: KpiIconGlyph;
  accentColor: string | null;
  favorableColor: string | null;
  unfavorableColor: string | null;
  showSparkline: boolean;
  sparkPoints: SparkPoint[];
}
