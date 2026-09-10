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
import { QueryFormData } from './adapters/supersetAdapter';

export type TextAlign = 'left' | 'center' | 'right';

export interface CustomTextCustomizeProps {
  /** The text to render. Newlines are preserved. */
  bodyText: string;
  fontSize: number;
  fontWeight: number;
  textAlign: TextAlign;
  /** Any CSS colour. Empty falls back to the theme's primary text colour. */
  textColor: string;
  /** Optional smaller line beneath the main text. */
  subText: string;
}

export type CustomTextFormData = QueryFormData & CustomTextCustomizeProps;

export interface CustomTextProps extends CustomTextCustomizeProps {
  width: number;
  height: number;
}
