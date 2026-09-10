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

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Value'),
              description: t('The aggregate drawn as the large number.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['adhoc_filters'],
      ],
    },
    {
      label: t('Display'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'cardLabel',
            config: {
              type: 'TextControl',
              label: t('Card label'),
              default: '',
              description: t(
                'Small grey caption above the number. Falls back to the metric label.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'numberFormat',
            config: {
              type: 'TextControl',
              label: t('Number format'),
              default: ',.1f',
              description: t(
                'D3 format applied to the value, e.g. ",.1f" for 8,920.4.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'unitSuffix',
            config: {
              type: 'TextControl',
              label: t('Unit suffix'),
              default: '',
              description: t(
                'Literal text appended after the formatted value, e.g. "M" when the column is already in millions.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'valueColor',
            config: {
              type: 'TextControl',
              label: t('Value colour'),
              default: null,
              description: t(
                'Optional CSS colour for the number. Leave empty to follow the theme text colour.',
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
