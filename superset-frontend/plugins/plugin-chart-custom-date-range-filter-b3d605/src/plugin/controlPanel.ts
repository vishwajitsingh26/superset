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
      label: t('Bounds'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'boundsStartColumn',
            config: {
              ...sharedControls.entity,
              label: t('Earliest date column'),
              description: t(
                'Column holding the earliest selectable date (one-row bounds view).',
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'boundsEndColumn',
            config: {
              ...sharedControls.entity,
              label: t('Latest date column'),
              description: t(
                'Column holding the latest selectable date. The calendar cannot open outside these two values.',
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['adhoc_filters'],
      ],
    },
    {
      label: t('Selection'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'defaultStart',
            config: {
              type: 'TextControl',
              label: t('Default start date'),
              default: '',
              description: t(
                'ISO date (YYYY-MM-DD) the control opens on. Clamped to the bounds.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'defaultEnd',
            config: {
              type: 'TextControl',
              label: t('Default end date'),
              default: '',
              description: t(
                'ISO date (YYYY-MM-DD) the control opens on. Clamped to the bounds.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'targetDateColumn',
            config: {
              type: 'TextControl',
              label: t('Target date column'),
              default: '',
              description: t(
                'Date column on the charts this filter drives. Emitted as explicit range filters alongside the time range; leave blank to send the time range only.',
              ),
              renderTrigger: false,
            },
          },
        ],
      ],
    },
    {
      label: t('Appearance'),
      expanded: false,
      controlSetRows: [
        [
          {
            name: 'accentColor',
            config: {
              type: 'TextControl',
              label: t('Selected range colour'),
              default: '',
              description: t(
                'Hex colour for the selected start and end dates. Falls back to the theme primary colour when blank.',
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
