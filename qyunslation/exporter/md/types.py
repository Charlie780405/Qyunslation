# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
from typing import Literal

ConvertEngineType = Literal["mineru", "docling", "identity", "mineru_deploy", "hpd"]

MD2DocxEngineType = Literal["python", "pandoc", "auto"] | None