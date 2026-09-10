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
} from '../adapters/supersetAdapter';
import { CK_LENS_PALETTE } from '../constants';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'groupby',
            config: {
              ...sharedControls.groupby,
              label: t('Dimensions'),
              description: t(
                'Columns to group by. First column = pie slices. ' +
                'Second column (if any) = breakdown inside tooltip.',
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Metric'),
              description: t('Metric to display in the pie chart'),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['adhoc_filters'],
        [
          {
            name: 'row_limit',
            config: {
              ...sharedControls.row_limit,
              label: t('Row limit'),
              description: t('Limits the number of rows that get retrieved.'),
              default: 1000,
            },
          },
        ],
      ],
    },
    {
      label: t('Display Options'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'topN',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('Number of Slices'),
              default: 5,
              description: t(
                'Total number of slices to display. If data has more items, ' +
                'remaining are grouped as "Others". E.g. 5 = top 4 + Others.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'showDecimals',
            config: {
              type: 'CheckboxControl',
              label: t('Show decimal values'),
              default: false,
              description: t(
                'When enabled, spend values are shown with 2 decimal places.',
              ),
              renderTrigger: true,
            },
          },
        ],
        ['currency_format'],
      ],
    },
    {
      label: t('Colors'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'customColors',
            config: {
              type: 'TextControl',
              label: t('Slice Colors'),
              default: CK_LENS_PALETTE.join(', '),
              description: t(
                'Comma-separated hex color values for pie slices (in order). ' +
                'E.g. "#8ECFFF, #EA6AA7, #FBD064, #F6B273, #60C0A6". ' +
                'If fewer colors than slices, colors will cycle.',
              ),
              renderTrigger: true,
            },
          },
        ],
      ],
    },
    {
      label: t('Tooltip'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'tooltipEnabled',
            config: {
              type: 'CheckboxControl',
              label: t('Enable Tooltip'),
              default: true,
              description: t(
                'Show tooltip on hover with slice details.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'tooltipBreakdownCol',
            config: {
              type: 'SelectControl',
              label: t('Tooltip Breakdown Column'),
              default: null,
              description: t(
                'Optional: Select a column to show as breakdown rows inside the tooltip. ' +
                'If not set, the second dimension from "Dimensions" is used. ' +
                'If neither is set, tooltip shows only the total value per slice.',
              ),
              // `ControlPanelState` is the callback's real first parameter; a
              // narrower hand-rolled type is rejected, and `any` is rejected by
              // the generator's own validator.
              mapStateToProps: (state: ControlPanelState) => ({
                choices: (state.datasource?.columns ?? []).map(col => [
                  col.column_name,
                  // `datasource.columns` is `ColumnMeta | QueryColumn` and only
                  // one of them carries a verbose name.
                  ('verbose_name' in col && col.verbose_name) || col.column_name,
                ]),
              }),
              renderTrigger: false,
              freeForm: false,
              validators: [],
            },
          },
        ],
        [
          {
            name: 'showTotalInTooltip',
            config: {
              type: 'CheckboxControl',
              label: t('Show Total in Tooltip'),
              default: true,
              description: t(
                'Display a "Total Spend" summary row at the bottom of tooltip.',
              ),
              renderTrigger: true,
            },
          },
        ],
      ],
    },
  ],
};

export default config;
