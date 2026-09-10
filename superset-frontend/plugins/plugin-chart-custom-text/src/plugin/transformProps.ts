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
import { ChartProps } from '../adapters/supersetAdapter';
import { CustomTextFormData, CustomTextProps, TextAlign } from '../types';

const DEFAULT_FONT_SIZE = 24;
const DEFAULT_FONT_WEIGHT = 600;

/** Everything comes from the control panel; the query result is ignored. */
export default function transformProps(
  chartProps: ChartProps,
): CustomTextProps {
  const { width, height, formData } = chartProps;
  const {
    bodyText = '',
    fontSize = DEFAULT_FONT_SIZE,
    fontWeight = DEFAULT_FONT_WEIGHT,
    textAlign = 'left',
    textColor = '',
    subText = '',
  } = formData as CustomTextFormData;

  return {
    width,
    height,
    bodyText,
    fontSize,
    fontWeight,
    textAlign: textAlign as TextAlign,
    textColor,
    subText,
  };
}
