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
import { DEFAULT_ROW_LIMIT, DEFAULT_VALUE_FORMAT } from '../constants';

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
              label: t('Account'),
              description: t('Column identifying each row, e.g. account name.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Total Spend'),
              description: t(
                'Metric drawn as the Total Spend value and as the proportional bar.',
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'secondaryMetric',
            config: {
              ...sharedControls.metric,
              label: t('% Change'),
              description: t(
                'Optional metric drawn as the colored % Change column. Leave unset to show a dash.',
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
              default: DEFAULT_ROW_LIMIT,
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
            name: 'barColor',
            config: {
              type: 'TextControl',
              label: t('Bar Color'),
              default: '',
              description: t(
                'Hex color for the proportional bar column. Leave blank to use the theme primary color.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'valueFormat',
            config: {
              type: 'TextControl',
              label: t('Value Format'),
              default: DEFAULT_VALUE_FORMAT,
              description: t(
                'D3 format string used to display the Total Spend value.',
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
