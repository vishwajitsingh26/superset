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
import { memo } from 'react';

interface WorldLandmassProps {
  fill: string;
}

// A deliberately simplified set of continent silhouettes in a 1000x500
// equirectangular canvas, matching `projectToUnitSquare`'s coordinate
// system. No coastline dataset was available to this package, and the
// design's own map draws flat, borderless landmasses at low fidelity
// itself, so a low-poly blob at each continent's rough position and size
// reads closer to the crop than a plain empty background would.
function WorldLandmass({ fill }: WorldLandmassProps) {
  return (
    <g fill={fill} stroke="none">
      <path d="M 130 90 C 180 60 260 70 300 110 C 340 150 330 190 300 210 C 320 230 300 260 260 250 C 230 245 210 220 190 230 C 160 245 140 220 150 190 C 120 170 110 130 130 90 Z" />
      <path d="M 250 260 C 290 260 310 300 300 340 C 310 380 290 420 260 430 C 235 435 220 400 225 360 C 215 330 225 290 250 260 Z" />
      <path d="M 460 100 C 500 90 530 100 520 130 C 540 150 520 170 500 165 C 480 175 460 160 455 140 C 445 125 450 110 460 100 Z" />
      <path d="M 470 190 C 520 180 560 200 555 240 C 570 280 555 330 530 370 C 510 390 480 380 470 350 C 450 320 455 280 460 250 C 450 220 455 200 470 190 Z" />
      <path d="M 560 80 C 650 60 760 70 820 110 C 860 140 850 180 810 190 C 830 220 800 250 760 240 C 730 260 690 250 670 220 C 630 230 600 210 590 180 C 560 160 550 120 560 80 Z" />
      <path d="M 800 340 C 840 330 880 345 890 370 C 895 395 870 410 840 405 C 815 410 795 390 800 365 Z" />
    </g>
  );
}

export default memo(WorldLandmass);
