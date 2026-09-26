#!/usr/bin/env python3
"""
Spanish Agent Quickstart and CSV Export Guide Generator

Generates a comprehensive Spanish-language documentation package for the OMI CLI,
including:
1. A quickstart guide for Spanish-speaking agents
2. A CSV export guide with practical examples
3. A sample CSV export utility that can be used with the OMI CLI

This script produces:
- docs/es/agent-quickstart.md
- docs/es/csv-export-guide.md
- scripts/omi_csv_export.py
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# =============================================================================
# DOCUMENTATION GENERATION
# =============================================================================

AGENT_QUICKSTART_ES = """\
# Guía de Inicio Rápido para Agentes (Español)

## Bienvenido a OMI

OMI (Open Machine Intelligence) es una plataforma de agentes autónomos que permite
la automatización de tareas, la integración con herramientas externas y la
colaboración entre agentes.

## Requisitos Previos

- Python 3.9 o superior
- `pip` instalado
- Conexión a internet
- Una cuenta en la plataforma OMI (opcional para uso local)

## Instalación

### Desde PyPI

```bash
pip install omi-cli
```

### Desde el repositorio

```bash
git clone https://github.com/BasedHardware/omi.git
cd omi
pip install -e .
```

### Verificación de la instalación

```bash
omi --version
# Debe mostrar: omi-cli 1.x.x
```

## Configuración Inicial

### 1. Crear el archivo de configuración

```bash
omi config init
```

Esto crea `~/.omi/config.yaml` con valores predeterminados.

### 2. Configurar la API Key

```bash
omi config set api_key "TU_API_KEY_AQUI"
```

O bien, edita manualmente `~/.omi/config.yaml`:

```yaml
api_key: "TU_API_KEY_AQUI"
default_model: "gpt-4"
max_tokens: 4096
temperature: 0.7
```

### 3. Verificar la configuración

```bash
omi config show
```

## Primeros Pasos

### Ejecutar un comando simple

```bash
# Saludo básico
omi agent run --prompt "Hola, ¿cómo estás?"

# Con modelo específico
omi agent run --prompt "Resume este texto: ..." --model gpt-4

# Con temperatura personalizada
omi agent run --prompt "Genera ideas creativas" --temperature 0.9
```

### Crear un agente personalizado

```bash
# Crear un nuevo agente
omi agent create --name "mi-agente" --description "Agente para análisis de datos"

# Ver agentes disponibles
omi agent list

# Ejecutar un agente específico
omi agent run --agent "mi-agente" --prompt "Analiza estos datos: ..."
```

### Usar herramientas (Tools)

```bash
# Listar herramientas disponibles
omi tools list

# Usar una herramienta específica
omi tools run --tool "web_search" --input "clima en Madrid"

# Configurar herramientas para un agente
omi agent configure --agent "mi-agente" --add-tool "web_search"
```

## Comandos Esenciales

| Comando | Descripción |
|---------|-------------|
| `omi agent run` | Ejecuta un agente con un prompt |
| `omi agent create` | Crea un nuevo agente |
| `omi agent list` | Lista todos los agentes |
| `omi agent delete` | Elimina un agente |
| `omi config init` | Inicializa la configuración |
| `omi config set` | Establece un valor de configuración |
| `omi config show` | Muestra la configuración actual |
| `omi tools list` | Lista herramientas disponibles |
| `omi tools run` | Ejecuta una herramienta |
| `omi logs tail` | Muestra los últimos registros |
| `omi logs export` | Exporta registros a CSV |

## Ejemplos Prácticos

### Ejemplo 1: Análisis de texto

```bash
omi agent run \\
  --prompt "Analiza el sentimiento de este texto: 'El producto es excelente'" \\
  --model gpt-4 \\
  --output json
```

### Ejemplo 2: Generación de código

```bash
omi agent run \\
  --prompt "Escribe una función en Python que calcule el factorial de un número" \\
  --model gpt-4 \\
  --output code
```

### Ejemplo 3: Chat interactivo

```bash
omi chat --agent "mi-agente"
```

### Ejemplo 4: Batch processing

```bash
# Procesar múltiples prompts desde un archivo
omi agent batch --input prompts.txt --output results.json
```

## Exportación de Datos (CSV)

Para exportar registros y resultados a formato CSV, consulta la
[Guía de Exportación CSV](csv-export-guide.md).

```bash
# Exportar registros recientes
omi logs export --format csv --output registros.csv

# Exportar resultados de agentes
omi agent export --agent "mi-agente" --format csv --output resultados.csv
```

## Solución de Problemas

### Error: "API key no válida"

```bash
# Verifica tu API key
omi config show

# Actualiza la API key
omi config set api_key "NUEVA_API_KEY"
```

### Error: "Modelo no encontrado"

```bash
# Lista modelos disponibles
omi models list

# Usa un modelo válido
omi agent run --prompt "Hola" --model gpt-4
```

### Error: "Permisos de escritura denegados"

```bash
# Verifica permisos del directorio de configuración
ls -la ~/.omi/

# Restablece permisos
chmod 700 ~/.omi/
chmod 600 ~/.omi/config.yaml
```

### Verbose logging

```bash
# Ejecutar con logging detallado
omi agent run --prompt "Hola" --verbose

# O establecer nivel de log global
omi config set log_level "DEBUG"
```

## Estructura de Directorios

```
~/.omi/
├── config.yaml          # Configuración principal
├── agents/              # Agentes personalizados
│   ├── mi-agente.yaml
│   └── otro-agente.yaml
├── logs/                # Registros de ejecución
│   ├── 2024-01-15.log
│   └── 2024-01-16.log
├── cache/               # Caché de respuestas
└── tools/               # Configuración de herramientas
```

## Recursos Adicionales

- [Documentación completa](https://docs.omi.dev/es/)
- [API Reference](https://docs.omi.dev/es/api/)
- [Ejemplos de agentes](https://github.com/BasedHardware/omi/tree/main/examples)
- [Comunidad](https://discord.gg/omi)

## Contribuir

Si deseas contribuir a OMI:

1. Fork del repositorio
2. Crea una rama de feature
3. Haz tus cambios
4. Escribe pruebas
5. Abre un Pull Request

```bash
git checkout -b feature/mi-cambio
# ... hacer cambios ...
git add .
git commit -m "feat: descripción del cambio"
git push origin feature/mi-cambio
```

## Licencia

OMI está licenciado bajo la licencia MIT. Consulta el archivo `LICENSE` para más detalles.
"""

CSV_EXPORT_GUIDE_ES = """\
# Guía de Exportación CSV (Español)

## Introducción

Esta guía explica cómo exportar datos de OMI al formato CSV (Comma-Separated Values),
un formato universal para intercambio de datos entre aplicaciones.

## Formatos de Exportación Disponibles

OMI soporta los siguientes formatos de exportación:

| Formato | Extensión | Uso Principal |
|---------|-----------|---------------|
| CSV | `.csv` | Hojas de cálculo, análisis de datos |
| JSON | `.json` | APIs, procesamiento programático |
| JSONL | `.jsonl` | Registros por línea, streaming |
| XML | `.xml` | Sistemas legados |
| Parquet | `.parquet` | Big data, análisis avanzado |

## Exportación de Registros (Logs)

### Exportar todos los registros

```bash
omi logs export --format csv --output registros_completos.csv
```

### Exportar registros de un rango de fechas

```bash
omi logs export \\
  --format csv \\
  --start "2024-01-01" \\
  --end "2024-01-31" \\
  --output registros_enero.csv
```

### Exportar registros de un agente específico

```bash
omi logs export \\
  --agent "mi-agente" \\
  --format csv \\
  --output registros_mi_agente.csv
```

### Filtrar por nivel de log

```bash
# Solo errores
omi logs export --level ERROR --format csv --output errores.csv