/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

// Datamaps bundles its own D3 (v3) and does not export it as an importable
// module -- `import * as d3 from "d3"` resolves to whatever D3 major version
// this checkout carries, which is a different, incompatible API (v3 used
// `d3.geo.path()`; v4+ moved that to a separate `d3-geo` package with a
// different call shape). Reaching it off the library instance is what keeps
// this working regardless of what else in the monorepo depends on D3.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type DatamapsD3 = any;

function datamapsD3(datamap: unknown): DatamapsD3 {
  return (datamap as { d3?: DatamapsD3 }).d3;
}

// Datamaps' own default projection frames the full globe, pole to pole, in
// the same height as the populated world -- roughly half the map is empty
// ocean and ice, and every landmass renders small. Centering on a band of
// latitudes people actually plot data at, and scaling to fill the canvas
// with that band, is what a design cropped to the inhabited world is
// actually asking for.
export function createProjection(
  datamap: unknown,
  width: number,
  height: number,
  options: { latTop?: number; latBottom?: number } = {},
) {
  const d3 = datamapsD3(datamap);
  const { latTop = 83, latBottom = -56 } = options;
  const degToRad = Math.PI / 180;
  const scale = width / (360 * degToRad);
  const latCenter = (latTop + latBottom) / 2;
  const projection = d3.geo
    .equirectangular()
    .scale(scale)
    .center([0, latCenter])
    .translate([width / 2, height / 2]);
  const path = d3.geo.path().projection(projection);
  return { path, projection };
}
