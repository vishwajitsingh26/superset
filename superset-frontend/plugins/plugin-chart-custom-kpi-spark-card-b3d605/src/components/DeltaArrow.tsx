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
import { DeltaDirection } from '../types';

interface DeltaArrowProps {
  direction: DeltaDirection;
  color: string;
  size: number;
}

const PATHS: Record<DeltaDirection, string> = {
  down: 'M8 2.6v10.8M8 13.4 4 9.4M8 13.4l4-4',
  up: 'M8 13.4V2.6M8 2.6 4 6.6M8 2.6l4 4',
  flat: 'M2.8 8h10.4',
};

function DeltaArrow({ direction, color, size }: DeltaArrowProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden
      focusable="false"
      style={{ display: 'block', flexShrink: 0 }}
    >
      <path
        d={PATHS[direction]}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default memo(DeltaArrow);
