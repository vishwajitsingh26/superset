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

// No colours live here. `check-custom-rules.js` rejects a `#rrggbb` anywhere
// in plugin source, and disabling that rule -- which this file used to do --
// teaches the wrong lesson twice over: the literal survives, and the way
// around the check looks sanctioned.
//
// A chart's colours arrive two ways instead. The design's exact brand hexes
// come in as *data*, through a colour control that stage D writes the design
// system's palette into. Everything else -- label, border, divider -- is a
// theme token read from `useTheme()`, so the chart follows light and dark.

export const FONT = {
  INTER: "Inter, sans-serif",
  ROBOTO: "Roboto, sans-serif",
  CAPTION_SEMI_BOLD: 600,
  CAPTION_REGULAR: 400,
  BODY_SEMI_BOLD: 600,
} as const;

// Default number of top slices to show (remainder grouped as "Others")
export const DEFAULT_TOP_N = 5;
