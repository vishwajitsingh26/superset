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
import { ControlSetItem } from "@superset-ui/chart-controls";
import { t } from "../../adapters/supersetAdapter";
import TabsEditor from "../../components/editor/TabsEditor";
import { validateWrapperTabs } from "../../utils/validation";

export const wrapperTabsControlSetItem: ControlSetItem = {
  name: "wrapper_tabs",
  config: {
    type: TabsEditor,
    label: t("Tabs"),
    description: t(
      "Manage the tabs in this wrapper. Each tab references an existing saved chart.",
    ),
    default: [],
    renderTrigger: true,
    validators: [
      (value: unknown) => {
        const result = validateWrapperTabs(value);
        return result === true ? false : result;
      },
    ],
    mapStateToProps: (state) => ({
      // Pass the wrapper's own slice id so the picker can exclude self.
      wrapperSliceId: state?.form_data?.slice_id,
    }),
  },
};
