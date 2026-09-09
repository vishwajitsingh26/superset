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
import {
  DEFAULT_FILTER_LABEL,
  DEFAULT_PLACEHOLDER,
  DEFAULT_ROW_LIMIT,
} from '../constants';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'filterColumn',
            config: {
              ...sharedControls.entity,
              label: t('Filter column'),
              description: t(
                'Column whose distinct values populate the dropdown.',
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
                'Maximum number of distinct values fetched for the dropdown.',
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
            name: 'filterLabel',
            config: {
              type: 'TextControl',
              label: t('Label'),
              default: DEFAULT_FILTER_LABEL,
              description: t('Text shown to the left of the dropdown.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'placeholderText',
            config: {
              type: 'TextControl',
              label: t('Empty selection text'),
              default: DEFAULT_PLACEHOLDER,
              description: t(
                'Shown when nothing is selected. An empty selection applies no filter.',
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
                'When enabled the dropdown emits an IN filter over every selected value.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'sortAscending',
            config: {
              type: 'CheckboxControl',
              label: t('Sort values ascending'),
              default: true,
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'defaultValues',
            config: {
              type: 'SelectControl',
              multi: true,
              freeForm: true,
              label: t('Default selection'),
              default: [],
              description: t(
                'Values pre-selected on load. Leave empty to select everything.',
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
