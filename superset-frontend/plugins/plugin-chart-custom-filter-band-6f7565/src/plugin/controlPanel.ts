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
} from '../adapters/supersetAdapter';

interface SlotDefaults {
  typeKey: string;
  targetColumn: string;
  label: string;
}

// One dropdown's three settings: which type-column value is "its" data, which
// column on other charts it filters, and the text shown while nothing is picked.
function slotRows(prefix: string, defaults: SlotDefaults) {
  return [
    [
      {
        name: `${prefix}TypeKey`,
        config: {
          type: 'TextControl' as const,
          label: t('Match value'),
          description: t(
            "Value in the type column that this dropdown's options are filtered to.",
          ),
          default: defaults.typeKey,
          validators: [],
        },
      },
    ],
    [
      {
        name: `${prefix}TargetColumn`,
        config: {
          type: 'TextControl' as const,
          label: t('Target column'),
          description: t('Column this dropdown filters on other charts.'),
          default: defaults.targetColumn,
          validators: [],
        },
      },
    ],
    [
      {
        name: `${prefix}Label`,
        config: {
          type: 'TextControl' as const,
          label: t('Placeholder label'),
          description: t(
            'Text shown when nothing is selected, e.g. "All Cloud Providers".',
          ),
          default: defaults.label,
          renderTrigger: true,
          validators: [],
        },
      },
    ],
  ];
}

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Options source'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'typeColumn',
            config: {
              type: 'SelectControl',
              label: t('Filter type column'),
              description: t(
                'Column that names which dropdown a row belongs to.',
              ),
              default: 'filter_type',
              freeForm: true,
              mapStateToProps: (state: ControlPanelState) => ({
                choices: (state.datasource?.columns ?? []).map(col => [
                  col.column_name,
                  ('verbose_name' in col && col.verbose_name) ||
                    col.column_name,
                ]),
              }),
              validators: [],
            },
          },
        ],
        [
          {
            name: 'valueColumn',
            config: {
              type: 'SelectControl',
              label: t('Filter value column'),
              description: t(
                'Column holding each option shown in the dropdown.',
              ),
              default: 'filter_value',
              freeForm: true,
              mapStateToProps: (state: ControlPanelState) => ({
                choices: (state.datasource?.columns ?? []).map(col => [
                  col.column_name,
                  ('verbose_name' in col && col.verbose_name) ||
                    col.column_name,
                ]),
              }),
              validators: [],
            },
          },
        ],
        [
          {
            name: 'row_limit',
            config: {
              ...sharedControls.row_limit,
              label: t('Row limit'),
              default: 1000,
            },
          },
        ],
      ],
    },
    {
      label: t('Cloud provider dropdown'),
      expanded: true,
      controlSetRows: slotRows('provider', {
        typeKey: 'provider',
        targetColumn: 'cloud_provider',
        label: 'All Cloud Providers',
      }),
    },
    {
      label: t('Account dropdown'),
      expanded: true,
      controlSetRows: slotRows('account', {
        typeKey: 'account',
        targetColumn: 'account_name',
        label: 'All Accounts',
      }),
    },
    {
      label: t('Region dropdown'),
      expanded: true,
      controlSetRows: slotRows('region', {
        typeKey: 'region',
        targetColumn: 'region',
        label: 'All Regions',
      }),
    },
    {
      label: t('Environment dropdown'),
      expanded: true,
      controlSetRows: slotRows('environment', {
        typeKey: 'environment',
        targetColumn: 'environment',
        label: 'All Environments',
      }),
    },
  ],
};

export default config;
