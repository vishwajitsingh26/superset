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
// No colours live here -- see the colour-control + theme-token fallback
// pattern used in components/BarCell.tsx instead.

// Matches the five accounts the design draws; a saved chart can raise it.
export const DEFAULT_ROW_LIMIT = 5;

// Mirrors the design system's `number_formats.money` value exactly.
export const DEFAULT_VALUE_FORMAT = '$,.0f';

// Percentage width of each of the table's four columns; must sum to 100.
export const COLUMN_WIDTHS = {
  dimension: 34,
  metric: 20,
  change: 18,
  bar: 28,
} as const;
