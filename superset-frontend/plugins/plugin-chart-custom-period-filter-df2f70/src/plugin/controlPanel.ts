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
  ControlPanelState,
  sharedControls,
  t,
  validateNonEmpty,
} from '../adapters/supersetAdapter';
import { DEFAULT_ROW_LIMIT } from '../constants';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'date_column',
            config: {
              type: 'SelectControl',
              label: t('Period column'),
              description: t(
                'Temporal column whose months populate the period dropdown and ' +
                  'which the emitted range filters on.',
              ),
              default: null,
              freeForm: false,
              validators: [validateNonEmpty],
              mapStateToProps: (state: ControlPanelState) => ({
                choices: (state.datasource?.columns ?? [])
                  .filter(col => col.is_dttm)
                  .map(col => [
                    col.column_name,
                    // `verbose_name` is on ColumnMeta but not QueryColumn, and
                    // `datasource.columns` is typed as the union of both.
                    ('verbose_name' in col && col.verbose_name) ||
                      col.column_name,
                  ]),
              }),
            },
          },
        ],
        [
          {
            name: 'groupby',
            config: {
              ...sharedControls.groupby,
              label: t('Filter dimensions'),
              description: t(
                'Categories offered inside the Filter panel. Leave empty to ' +
                  'show the period dropdown only.',
              ),
              validators: [],
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
              description: t(
                'Maximum rows scanned for distinct filter-panel values.',
              ),
              default: DEFAULT_ROW_LIMIT,
            },
          },
        ],
      ],
    },
    {
      label: t('Display options'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'show_filter_button',
            config: {
              type: 'CheckboxControl',
              label: t('Show Filter button'),
              default: true,
              description: t(
                'Renders the funnel button that opens the filter panel next to ' +
                  'the period dropdown.',
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
