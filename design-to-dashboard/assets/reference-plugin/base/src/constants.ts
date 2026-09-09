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
/* eslint-disable theme-colors/no-literal-colors */

// CK Lens 5-color palette for donut chart. Order: light-blue, pink, yellow, orange, green
export const CK_LENS_PALETTE = [
  '#8ECFFF',
  '#EA6AA7',
  '#FBD064',
  '#F6B273',
  '#60C0A6',
] as const;

export const COLORS = {
  'AWS Spend': '#8ECFFF',
  'Azure Spend': '#F6B273',
  'GCP Spend': '#60C0A6',
  FALLBACK_1: '#EA6AA7',
  FALLBACK_2: '#FBD064',
} as const;

export const CHART_COLORS = {
  LABEL_PRIMARY: '#050505',
  LABEL_SECONDARY: '#737373',
  BORDER: '#D9D9D9',
  DIVIDER: '#F0F0F0',
  TOTAL_LABEL: '#737373',
  TOTAL_VALUE: '#050505',
  FALLBACK_DOT: '#ccc',
} as const;

export const FONT = {
  INTER: 'Inter, sans-serif',
  ROBOTO: 'Roboto, sans-serif',
  CAPTION_SEMI_BOLD: 600,
  CAPTION_REGULAR: 400,
  BODY_SEMI_BOLD: 600,
} as const;

// Default number of top slices to show (remainder grouped as "Others")
export const DEFAULT_TOP_N = 5;
