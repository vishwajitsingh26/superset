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
import type {
  ControlPanelConfig,
  ControlPanelState,
} from '../adapters/supersetAdapter';
import { t } from '../adapters/supersetAdapter';

// `ControlPanelState` is the callback's real first parameter; a narrower
// hand-rolled type is rejected, and `any` is rejected by this codebase.
const columnChoices = (state: ControlPanelState): [string, string][] =>
  (state.datasource?.columns ?? []).map(col => [
    col.column_name,
    ('verbose_name' in col && col.verbose_name) || col.column_name,
  ]);

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Date bounds'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'rangeStartColumn',
            config: {
              type: 'SelectControl',
              label: t('Range start column'),
              description: t(
                'Column on the bounds dataset holding the earliest available date.',
              ),
              default: 'range_start',
              freeForm: false,
              mapStateToProps: (state: ControlPanelState) => ({
                choices: columnChoices(state),
              }),
              validators: [],
            },
          },
        ],
        [
          {
            name: 'rangeEndColumn',
            config: {
              type: 'SelectControl',
              label: t('Range end column'),
              description: t(
                'Column on the bounds dataset holding the latest available date.',
              ),
              default: 'range_end',
              freeForm: false,
              mapStateToProps: (state: ControlPanelState) => ({
                choices: columnChoices(state),
              }),
              validators: [],
            },
          },
        ],
      ],
    },
  ],
};

export default config;
