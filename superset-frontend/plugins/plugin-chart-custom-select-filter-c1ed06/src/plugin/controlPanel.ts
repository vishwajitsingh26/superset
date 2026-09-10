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
            name: 'groupby',
            config: {
              ...sharedControls.entity,
              label: t('Category'),
              description: t(
                'Column whose distinct values fill the dropdown. Repopulates ' +
                  'from whichever dataset is attached.',
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
              description: t('Maximum number of options to load.'),
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
            name: 'filterLabel',
            config: {
              type: 'TextControl',
              label: t('Label'),
              default: t('Filter'),
              description: t('Grey prefix shown before the dropdown.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'allLabel',
            config: {
              type: 'TextControl',
              label: t('Unset label'),
              default: t('All'),
              description: t(
                'Text shown when nothing is selected, e.g. "All platforms".',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'multiSelect',
            config: {
              type: 'CheckboxControl',
              label: t('Allow multiple selections'),
              default: true,
              description: t(
                'When enabled the dropdown emits an IN filter over several ' +
                  'values instead of one.',
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
