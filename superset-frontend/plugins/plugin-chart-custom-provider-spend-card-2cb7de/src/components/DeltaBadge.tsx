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
import { Delta } from '../ProviderSpendCardStyles';

export interface DeltaBadgeProps {
  text: string;
  positive: boolean;
}

function DeltaBadge({ text, positive }: DeltaBadgeProps) {
  return (
    <Delta $positive={positive} data-testid="spend-card-delta">
      <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
        <path
          d={positive ? 'M4 0 L8 7 L0 7 Z' : 'M4 8 L0 1 L8 1 Z'}
          fill="currentColor"
        />
      </svg>
      <span>{text}</span>
    </Delta>
  );
}

export default memo(DeltaBadge);
