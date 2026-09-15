/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance
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
  Behavior,
  ChartMetadata,
  ChartPlugin,
  t,
} from "../adapters/supersetAdapter";
import buildQuery from "./buildQuery";
import controlPanel from "./controlPanel";
import transformProps from "./transformProps";
import { CustomWrapperChartFormData } from "./types";
import thumbnail from "../images/thumbnail.png";

const metadata = new ChartMetadata({
  name: t("Tabbed Widget"),
  category: t("Custom Charts"),
  description: t(
    "A widget that hosts multiple existing charts as tabs, with shared filters, expand, and download. " +
      "Each tab references an existing saved chart by id.",
  ),
  behaviors: [
    Behavior.InteractiveChart,
    Behavior.NativeFilter,
    Behavior.DrillToDetail,
    Behavior.DrillBy,
  ],
  tags: [t("Custom Charts"), t("Composite"), t("Tabs")],
  thumbnail,
});

// A wrapper draws no data of its own. It says so by returning no query object
// from `buildQuery`, not by a flag on the metadata: `skipDataFetch` is not a
// field of `ChartMetadataConfig` and setting it fails the build.

export default class CustomWrapperChartPlugin extends ChartPlugin<CustomWrapperChartFormData> {
  constructor() {
    super({
      buildQuery,
      controlPanel,
      loadChart: () => import("./WrapperChart").then((module) => module.default),
      metadata,
      transformProps,
    });
  }
}
