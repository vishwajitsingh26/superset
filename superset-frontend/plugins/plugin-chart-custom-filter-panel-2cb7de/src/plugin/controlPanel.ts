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
import { DEFAULT_BUTTON_LABEL, DEFAULT_ROW_LIMIT } from '../constants';

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
              label: t('Filter Fields'),
              description: t(
                'Columns offered inside the filter panel. One dropdown is ' +
                  'rendered per column, in this order.',
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
                'Rows scanned to build the option lists for each field.',
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
            name: 'buttonLabel',
            config: {
              type: 'TextControl',
              label: t('Button label'),
              default: DEFAULT_BUTTON_LABEL,
              description: t('Text shown on the collapsed filter button.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'accentColor',
            config: {
              type: 'TextControl',
              label: t('Accent colour'),
              default: null,
              description: t(
                'Hex colour for the active-filter badge. Falls back to the ' +
                  'theme primary colour when empty.',
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
