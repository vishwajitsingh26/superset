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
  ControlPanelConfig,
  sharedControls,
  t,
  validateNonEmpty,
} from "../adapters/supersetAdapter";
import {
  DEFAULT_GRAIN,
  DEFAULT_GRAIN_COUNTS,
  GRAIN_LABELS,
  GRAIN_ORDER,
} from "../constants";
import { GrainKey } from "../types";

const GRAIN_CHOICES: [GrainKey, string][] = GRAIN_ORDER.map((key) => [
  key,
  GRAIN_LABELS[key],
]);

// One row per grain: the label is the only thing that changes between them,
// so it is generated rather than pasted five times and left to drift.
function countControl(name: string, grain: GrainKey) {
  return {
    name,
    config: {
      type: "TextControl",
      isInt: true,
      label: t("%s: periods to show", GRAIN_LABELS[grain]),
      description: t(
        "How many periods to show, ending at the selected month, when this " +
          "grain is chosen in the grain dropdown.",
      ),
      default: DEFAULT_GRAIN_COUNTS[grain],
      renderTrigger: false,
    },
  };
}

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t("Period"),
      expanded: true,
      controlSetRows: [
        [
          {
            // `sharedControls.entity` is dataset-aware -- it lists the
            // dataset's own columns rather than a hand-rolled
            // `mapStateToProps`, the same way the committed date-range
            // filter picks its bounds columns.
            name: "date_column",
            config: {
              ...sharedControls.entity,
              label: t("Date Column"),
              description: t(
                "Temporal column that drives everything: builds the month " +
                  "dropdown from this column's own MIN/MAX and emits the range " +
                  "filter. Use the SAME column target charts have as their " +
                  "temporal X-axis, or the dropdown and the filtered charts " +
                  "will disagree about what a month contains.",
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: "enabled_grains",
            config: {
              type: "SelectControl",
              multi: true,
              freeForm: false,
              label: t("Enabled Grains"),
              description: t(
                "Which grains appear in the grain dropdown, in display order.",
              ),
              default: GRAIN_ORDER,
              choices: GRAIN_CHOICES,
              clearable: false,
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: "default_grain",
            config: {
              type: "SelectControl",
              label: t("Default Grain"),
              description: t("Grain applied on first load."),
              default: DEFAULT_GRAIN,
              choices: GRAIN_CHOICES,
              clearable: false,
              validators: [validateNonEmpty],
            },
          },
        ],
        [countControl("daily_count", "daily")],
        [countControl("weekly_count", "weekly")],
        [countControl("monthly_count", "monthly")],
        [countControl("quarterly_count", "quarterly")],
        [countControl("yearly_count", "yearly")],
      ],
    },
  ],
};

export default config;
