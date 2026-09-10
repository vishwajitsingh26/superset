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
import { DEFAULT_ROW_LIMIT } from '../constants';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'x_axis',
            config: {
              ...sharedControls.x_axis,
              label: t('Period column'),
              description: t(
                'Temporal column whose distinct months populate the picker.',
              ),
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
              description: t(
                'Rows scanned to build the list of available periods.',
              ),
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
            name: 'default_to_latest',
            config: {
              type: 'CheckboxControl',
              label: t('Start on latest period'),
              default: true,
              description: t(
                'Apply the newest available month when the dashboard loads.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'placeholder_text',
            config: {
              type: 'TextControl',
              label: t('Placeholder'),
              default: 'Select month',
              description: t('Text shown when no period is selected.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'accent_color',
            config: {
              type: 'TextControl',
              label: t('Accent color'),
              default: null,
              description: t(
                'Hex color for the focused and hovered outline. Falls back to the theme primary color when empty.',
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
