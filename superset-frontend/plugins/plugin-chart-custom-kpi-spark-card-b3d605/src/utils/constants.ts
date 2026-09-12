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

// Geometry and type scale come from the run's design-system contract:
// card 12px radius / 20px padding / 1px border, value 30px/700,
// label 13px/500, caption 11px/400. No colours live here -- accent and
// delta colours arrive as data through controls and fall back to theme tokens.
export const SIZES = {
  cardRadius: 12,
  cardPadding: 20,
  iconSize: 20,
  labelGap: 8,
  valueGap: 10,
  bottomGap: 12,
  arrowSize: 16,
  sparkWidth: 100,
  sparkMinWidth: 56,
  sparkHeight: 40,
  sparkMinHeight: 24,
  deltaMinWidth: 96,
  labelFontSize: 13,
  valueFontSize: 30,
  deltaFontSize: 14,
  captionFontSize: 11,
} as const;

export const DEFAULT_ROW_LIMIT = 1000;
export const DEFAULT_VALUE_FORMAT = '$,.0f';
export const DEFAULT_PERCENT_FORMAT = ',.1f';
export const DEFAULT_SUB_CAPTION = 'vs. last month';
